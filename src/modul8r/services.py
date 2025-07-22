import asyncio
import base64
import io
from typing import List, Optional, Tuple, Dict, Any
from pdf2image import convert_from_bytes
from openai import AsyncOpenAI
import os
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .config import settings
from .logging_config import get_logger


class OpenAIService:
    def __init__(self, api_key: Optional[str] = None):
        self.client = AsyncOpenAI(api_key=api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY"))
        self.semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        self.logger = get_logger("openai_service")
    
    async def get_vision_models(self) -> List[str]:
        """Get list of all available models from OpenAI."""
        self.logger.info("Fetching available models from OpenAI API")
        try:
            models = await self.client.models.list()
            model_ids = []
            
            for model in models.data:
                model_ids.append(model.id)
            
            # Sort alphabetically
            model_ids.sort()
            
            self.logger.info("Successfully fetched models", model_count=len(model_ids))
            return model_ids
        except Exception as e:
            self.logger.warning("Failed to fetch models from API, using fallback", error=str(e))
            # Fallback to common vision models if API call fails
            return ["gpt-4o", "gpt-4o-mini"]
    
    @retry(
        stop=stop_after_attempt(settings.retry_max_attempts),
        wait=wait_exponential(
            multiplier=settings.retry_base_delay,
            max=settings.retry_max_delay
        ),
        retry=retry_if_exception_type((Exception,))
    )
    async def _process_single_image(
        self,
        page_index: int,
        image_base64: str,
        model: str,
        detail: str
    ) -> Tuple[int, str]:
        """Process a single image with retry logic and rate limiting."""
        system_prompt = (
            "You are an expert at converting scanned tabletop RPG (TTRPG) adventure modules "
            "and game documents into clean, structured Markdown format. Your task is to:"
            "\n\n"
            "1. Accurately transcribe all text content from the image\n"
            "2. Preserve the document structure using appropriate Markdown formatting\n"
            "3. Use proper heading levels (# ## ###) for sections and subsections\n"
            "4. Format tables, stat blocks, and game mechanics clearly\n"
            "5. Maintain any special formatting for game rules, spells, or abilities\n"
            "6. Include any important visual elements as descriptions in [brackets]\n"
            "7. Preserve page layout and organization as much as possible\n"
            "\n"
            "Return ONLY the converted Markdown content, no additional commentary or explanation."
        )
        
        self.logger.info("Processing page", page=page_index + 1, model=model, detail=detail)
        
        async with self.semaphore:
            try:
                async with asyncio.timeout(settings.openai_timeout):
                    response = await self.client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {
                                "role": "user", 
                                "content": [
                                    {
                                        "type": "image_url",
                                        "image_url": {
                                            "url": f"data:image/png;base64,{image_base64}",
                                            "detail": detail
                                        }
                                    }
                                ]
                            }
                        ],
                        max_tokens=settings.openai_max_tokens,
                        temperature=settings.openai_temperature
                    )
                
                content = response.choices[0].message.content or ""
                self.logger.info("Successfully processed page", page=page_index + 1, content_length=len(content))
                return page_index, content
                
            except Exception as e:
                self.logger.error("Failed to process page", page=page_index + 1, error=str(e))
                raise


    async def process_images_batch(
        self,
        images_base64: List[str],
        model: str = "gpt-4o",
        detail: str = "high"
    ) -> List[str]:
        """Process multiple images concurrently using TaskGroup."""
        if not images_base64:
            return []
        
        total_pages = len(images_base64)
        self.logger.info("Starting batch processing", total_pages=total_pages, model=model, concurrency=settings.max_concurrent_requests)
        
        try:
            async with asyncio.TaskGroup() as tg:
                tasks = [
                    tg.create_task(
                        self._process_single_image(i, image_base64, model, detail)
                    )
                    for i, image_base64 in enumerate(images_base64)
                ]
            
            # Collect results from completed tasks
            results = [None] * total_pages
            for task in tasks:
                page_index, content = task.result()
                results[page_index] = content
            
            # Filter out None results and empty content
            final_results = [content for content in results if content and content.strip()]
            
            self.logger.info("Completed batch processing", 
                           total_pages=total_pages, 
                           successful_pages=len(final_results))
            
            return final_results
            
        except Exception as e:
            # Handle any exception from TaskGroup
            self.logger.error("Error during batch processing", error=str(e))
            
            # Try to salvage partial results from successful tasks if they exist
            if 'tasks' in locals():
                successful_results = []
                failed_pages = []
                
                for i, task in enumerate(tasks):
                    try:
                        if task.done() and not task.cancelled() and not task.exception():
                            page_index, content = task.result()
                            successful_results.append((page_index, content))
                        else:
                            failed_pages.append(i + 1)
                            if task.done() and task.exception():
                                self.logger.error("Task failed with exception", 
                                                page=i + 1, 
                                                error=str(task.exception()))
                    except Exception as task_e:
                        self.logger.error("Error checking task result", page=i + 1, error=str(task_e))
                        failed_pages.append(i + 1)
                
                if successful_results:
                    # Sort and return partial results
                    successful_results.sort(key=lambda x: x[0])
                    partial_results = [content for _, content in successful_results if content and content.strip()]
                    
                    self.logger.warning("Partial processing completed with errors", 
                                      successful_pages=len(partial_results),
                                      failed_pages=len(failed_pages),
                                      total_pages=total_pages)
                    return partial_results
            
            # If no partial results available, re-raise the exception
            self.logger.error("All pages failed to process")
            raise Exception(f"Failed to process all {total_pages} pages: {str(e)}")


class PDFService:
    def __init__(self):
        self.logger = get_logger("pdf_service")
    
    def pdf_to_images(self, pdf_bytes: bytes) -> List[bytes]:
        """Convert PDF bytes to a list of image bytes (PNG format)."""
        self.logger.info("Converting PDF to images", pdf_size=len(pdf_bytes))
        try:
            # Convert PDF to PIL Images
            images = convert_from_bytes(
                pdf_bytes,
                dpi=settings.pdf_dpi,
                fmt=settings.pdf_format
            )
            
            image_bytes_list = []
            for i, image in enumerate(images):
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format=settings.pdf_format, optimize=True)
                image_bytes_list.append(img_byte_arr.getvalue())
            
            self.logger.info("Successfully converted PDF to images", page_count=len(image_bytes_list))
            return image_bytes_list
        except Exception as e:
            self.logger.error("Failed to convert PDF to images", error=str(e))
            raise Exception(f"Failed to convert PDF to images: {str(e)}")
    
    def images_to_base64(self, image_bytes_list: List[bytes]) -> List[str]:
        """Convert list of image bytes to base64 strings."""
        self.logger.info("Converting images to base64", image_count=len(image_bytes_list))
        base64_images = [base64.b64encode(img_bytes).decode('utf-8') for img_bytes in image_bytes_list]
        self.logger.info("Successfully converted images to base64")
        return base64_images