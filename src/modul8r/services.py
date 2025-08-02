# services.py
import asyncio
import base64
import io
import os
from typing import List, Optional, Tuple

from openai import AsyncOpenAI
from pdf2image import convert_from_bytes
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from .config import settings
from .logging_config import get_logger


class OpenAIService:
    def __init__(self, api_key: Optional[str] = None):
        self.client = AsyncOpenAI(api_key=api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY"))
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        self.logger = get_logger("openai_service")

    async def get_vision_models(self) -> List[str]:
        """Get list of all available vision models from OpenAI via Responses API-compatible models."""
        self.logger.info("Fetching model list from OpenAI")
        try:
            models = await self.client.models.list()
            model_ids: List[str] = []

            for model in models.data:
                if model.id.startswith("gpt-4") or model.id.startswith("o"):  # Vision-capable prefixes
                    self.logger.debug("Found vision model", model_id=model.id)
                    model_ids.append(model.id)

            model_ids.sort()
            self.logger.info("Fetched models", model_count=len(model_ids))
            return model_ids
        except Exception as e:
            self.logger.warning("Failed to fetch models from API", error=str(e))
            raise Exception(f"Failed to fetch models: {str(e)}")

    def _parse_response_text(self, response) -> str:
        """Normalize getting text output from Responses API response."""
        if getattr(response, "output_text", None):
            return response.output_text
        outputs = getattr(response, "output", []) or []
        parts: List[str] = []
        for item in outputs:
            if hasattr(item, "content") and isinstance(item.content, str):
                parts.append(item.content)
            elif isinstance(item, dict):
                text = item.get("content") or item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)

    @retry(
        stop=stop_after_attempt(settings.retry_max_attempts),
        wait=wait_exponential(multiplier=settings.retry_base_delay, max=settings.retry_max_delay),
        retry=retry_if_exception_type((Exception,)),
        reraise=True,
    )
    async def _process_single_image(
        self, page_index: int, image_base64: str, model: str, detail: str
    ) -> Tuple[int, str]:
        """Process a single image with retry logic and rate limiting using the Responses API."""
        system_prompt = (
            "You are an expert at converting text content from scanned tabletop RPG adventure "
            "modules and other game books to clean Markdown format. Your task is to:\n\n"
            "1. Accurately transcribe all text content from the image\n"
            "2. Preserve the document structure using appropriate Markdown formatting\n"
            "3. Use proper heading levels (# ## ###) for sections and subsections\n"
            "4. Format tables, stat blocks, and game mechanics clearly\n"
            "5. Maintain any special formatting for game rules, spells, or abilities\n"
            "6. Include any important visual elements as descriptions in [brackets]\n"
            "7. Preserve page layout and organization as much as possible\n"
            "8. Rely on headings as separators rather than triple-dashes or other characters\n\n"
            "Return ONLY the converted Markdown content with no additional commentary or explanation and without outer code fences."
        )

        self.logger.info("Processing page", page=page_index + 1, model=model, detail=detail)

        async with self.semaphore:
            try:
                async with asyncio.timeout(settings.openai_timeout):
                    # Build the input for the Responses API: merge system instructions as input_text
                    user_content = [
                        {"type": "input_text", "text": system_prompt},
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{image_base64}",
                            "detail": detail,
                        },
                    ]

                    request_kwargs = {
                        "model": model,
                        "input": [{"role": "user", "content": user_content}],
                    }

                    if model.startswith("o"):
                        # o-series models historically use max_completion_tokens semantics
                        request_kwargs["max_completion_tokens"] = getattr(settings, "openai_max_tokens", 100000)
                        # Do not set temperature if not supported / default behavior
                        self.logger.info("Using o-series model parameters", model=model, page=page_index + 1)
                    else:
                        request_kwargs["max_output_tokens"] = getattr(settings, "openai_max_tokens", 32768)
                        request_kwargs["temperature"] = settings.openai_temperature

                    response = await self.client.responses.create(**request_kwargs)

                content = self._parse_response_text(response) or ""
                self.logger.info(
                    "Successfully processed page",
                    page=page_index + 1,
                    content_length=len(content),
                )
                return page_index, content

            except Exception as e:
                self.logger.error("Failed to process page", page=page_index + 1, error=str(e))
                raise

    async def process_images_batch(
        self, images_base64: List[str], model: str = "gpt-4.1-nano", detail: str = "high"
    ) -> List[str]:
        """Process multiple images concurrently using TaskGroup."""
        if not images_base64:
            return []

        total_pages = len(images_base64)

        try:
            async with asyncio.TaskGroup() as tg:
                tasks = [
                    tg.create_task(self._process_single_image(i, image_base64, model, detail))
                    for i, image_base64 in enumerate(images_base64)
                ]

            results = [''] * total_pages
            for task in tasks:
                page_index, content = task.result()
                results[page_index] = content

            final_results = [content for content in results if content and content.strip()]
            return final_results

        except Exception as e:
            self.logger.error("Error during batch processing", error=str(e))

            if "tasks" in locals():
                successful_results: List[Tuple[int, str]] = []
                failed_count = 0

                for i, task in enumerate(tasks):
                    try:
                        if task.done() and not task.cancelled():
                            if task.exception() is None:
                                page_index, content = task.result()
                                successful_results.append((page_index, content))
                            else:
                                failed_count += 1
                                self.logger.debug("Task failed", page=i + 1, error=str(task.exception()))
                        else:
                            failed_count += 1
                    except Exception as task_e:
                        failed_count += 1
                        self.logger.debug("Error checking task result", page=i + 1, error=str(task_e))

                if successful_results:
                    successful_results.sort(key=lambda x: x[0])
                    partial_results = [content for _, content in successful_results if content and content.strip()]

                    self.logger.warning(
                        "Partial processing completed with errors",
                        successful_pages=len(partial_results),
                        failed_pages=failed_count,
                        total_pages=total_pages,
                    )
                    return partial_results

            self.logger.error("No pages could be processed successfully")
            return []

    async def _combine_markdown_versions(self, page_index: int, versions: List[str], model: str) -> Tuple[int, str]:
        """Combine multiple Markdown versions using the Responses API."""
        system_prompt = (
            "You are an expert at consolidating multiple attempts to extract text "
            "from a scanned TTRPG module page. Given up to three Markdown "
            "versions, produce the most complete and accurate combined version. "
            "Return ONLY the merged Markdown without commentary."
        )

        user_prompt = "\n\n".join(f"Version {i + 1}:\n{md}" for i, md in enumerate(versions))
        combined_input_text = f"{system_prompt}\n\n{user_prompt}"

        async with self.semaphore:
            try:
                async with asyncio.timeout(settings.openai_timeout):
                    request_kwargs = {
                        "model": model,
                        "input": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "input_text", "text": combined_input_text},
                                ],
                            }
                        ],
                    }

                    if model.startswith("o"):
                        request_kwargs["max_completion_tokens"] = getattr(settings, "openai_max_tokens", 100000)
                    else:
                        request_kwargs["max_output_tokens"] = getattr(settings, "openai_max_tokens", 32768)
                        request_kwargs["temperature"] = settings.openai_temperature

                    response = await self.client.responses.create(**request_kwargs)

                content = self._parse_response_text(response) or ""
                self.logger.info("Combined page", page=page_index + 1, content_length=len(content))
                return page_index, content
            except Exception as e:
                self.logger.error("Failed to combine page", page=page_index + 1, error=str(e))
                raise

    async def _process_page_fan_out_fan_in(
        self,
        page_index: int,
        image_base64: str,
        fan_out_models: List[str],
        fan_in_model: str,
        detail: str,
    ) -> Tuple[int, str]:
        """Process a single page using fan-out/fan-in."""
        fan_out_tasks = [
            asyncio.create_task(self._process_single_image(page_index, image_base64, m, detail)) for m in fan_out_models
        ]

        results: List[str] = []
        for task in fan_out_tasks:
            try:
                _, content = await task
                if content and content.strip():
                    results.append(content)
            except Exception as e:
                self.logger.error("Fan-out processing failed", page=page_index + 1, error=str(e))

        if not results:
            return page_index, ""

        return await self._combine_markdown_versions(page_index, results, fan_in_model)

    async def process_images_fan_out_fan_in(
        self,
        images_base64: List[str],
        fan_out_models: Optional[List[str]] = None,
        fan_in_model: str = "gpt-4.1-nano",
        detail: str = "high",
    ) -> List[str]:
        """Process images using fan-out/fan-in with optional model list."""
        if not images_base64:
            return []

        fan_out_models = fan_out_models or [settings.openai_default_model] * 3
        total_pages = len(images_base64)

        try:
            async with asyncio.TaskGroup() as tg:
                tasks = [
                    tg.create_task(self._process_page_fan_out_fan_in(i, img, fan_out_models, fan_in_model, detail))
                    for i, img in enumerate(images_base64)
                ]

            results = ["" for _ in range(total_pages)]
            for task in tasks:
                page_index, content = task.result()
                results[page_index] = content

            return [r for r in results if r.strip()]
        except Exception as e:
            self.logger.error("Error during fan-out/fan-in processing", error=str(e))
            return []


class PDFService:
    def __init__(self):
        self.logger = get_logger("pdf_service")

    def pdf_to_images(self, pdf_bytes: bytes) -> List[bytes]:
        """Convert PDF bytes to a list of image bytes (PNG format)."""
        try:
            images = convert_from_bytes(pdf_bytes, dpi=settings.pdf_dpi, fmt=settings.pdf_format)

            image_bytes_list: List[bytes] = []
            for i, image in enumerate(images):
                self.logger.info(f"Converting page {i + 1}/{len(images)} to image")
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format=settings.pdf_format, optimize=True)
                image_bytes_list.append(img_byte_arr.getvalue())

            return image_bytes_list
        except Exception as e:
            self.logger.error("Failed to convert PDF to images", error=str(e))
            raise Exception(f"Failed to convert PDF to images: {str(e)}")

    def images_to_base64(self, image_bytes_list: List[bytes]) -> List[str]:
        """Convert list of image bytes to base64 strings."""
        return [base64.b64encode(img_bytes).decode("utf-8") for img_bytes in image_bytes_list]
