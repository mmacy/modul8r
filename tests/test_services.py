import pytest
import base64
from unittest.mock import Mock, patch, AsyncMock
from io import BytesIO
from PIL import Image

from src.modul8r.services import OpenAIService, PDFService


class TestOpenAIService:
    @pytest.fixture
    def mock_openai_client(self):
        with patch("src.modul8r.services.AsyncOpenAI") as mock_client:
            yield mock_client.return_value

    def test_init_with_api_key(self):
        service = OpenAIService(api_key="test-key")
        assert service.client is not None

    def test_init_without_api_key(self):
        with patch.dict("os.environ", {"OPENAI_API_KEY": "env-key"}):
            service = OpenAIService()
            assert service.client is not None

    @pytest.mark.asyncio
    async def test_get_vision_models_success(self, mock_openai_client):
        # Mock the models list response
        mock_model1 = Mock()
        mock_model1.id = "gpt-4o"
        mock_model2 = Mock()
        mock_model2.id = "gpt-4o-mini"
        mock_model3 = Mock()
        mock_model3.id = "gpt-3.5-turbo"  # Should be filtered out

        mock_response = Mock()
        mock_response.data = [mock_model1, mock_model2, mock_model3]
        mock_openai_client.models.list = AsyncMock(return_value=mock_response)

        service = OpenAIService()
        service.client = mock_openai_client

        models = await service.get_vision_models()

        assert "gpt-4o" in models
        assert "gpt-4o-mini" in models
        assert "gpt-4o" in models
        assert "gpt-4o-mini" in models

        # Only vision models should be returned
        assert "gpt-3.5-turbo" not in models

    @pytest.mark.asyncio
    async def test_get_vision_models_failure(self, mock_openai_client):
        mock_openai_client.models.list.side_effect = Exception("API Error")

        service = OpenAIService()
        service.client = mock_openai_client

        # Should raise exception when API fails
        with pytest.raises(Exception) as exc_info:
            await service.get_vision_models()

        assert "Failed to fetch models" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_images_batch_success(self, mock_openai_client):
        # Mock the chat completions response
        mock_choice = Mock()
        mock_choice.message.content = "# Test Markdown Content"

        mock_response = Mock()
        mock_response.choices = [mock_choice]

        mock_openai_client.chat.completions.create = AsyncMock(return_value=mock_response)

        service = OpenAIService()
        service.client = mock_openai_client

        result = await service.process_images_batch(["base64_image_data"])

        assert result == ["# Test Markdown Content"]
        mock_openai_client.chat.completions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_images_batch_failure(self, mock_openai_client):
        mock_openai_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))

        service = OpenAIService()
        service.client = mock_openai_client

        result = await service.process_images_batch(["base64_image_data"])

        # Should return empty list when all processing fails
        assert result == []


class TestPDFService:
    def test_images_to_base64(self):
        # Create test image bytes
        img = Image.new("RGB", (100, 100), color="red")
        img_bytes = BytesIO()
        img.save(img_bytes, format="PNG")
        img_bytes_data = img_bytes.getvalue()

        service = PDFService()
        result = service.images_to_base64([img_bytes_data])

        assert len(result) == 1
        assert isinstance(result[0], str)
        # Verify it's valid base64
        assert base64.b64decode(result[0])

    @patch("src.modul8r.services.convert_from_bytes")
    def test_pdf_to_images_success(self, mock_convert):
        # Mock PIL Image
        mock_image = Mock()
        mock_convert.return_value = [mock_image]

        # Mock the save method to write to BytesIO
        def mock_save(buffer, format, **kwargs):
            buffer.write(b"fake_image_data")

        mock_image.save = mock_save

        pdf_bytes = b"fake_pdf_data"
        service = PDFService()
        result = service.pdf_to_images(pdf_bytes)

        assert len(result) == 1
        assert result[0] == b"fake_image_data"
        mock_convert.assert_called_once_with(pdf_bytes, dpi=300, fmt="PNG")

    @patch("src.modul8r.services.convert_from_bytes")
    def test_pdf_to_images_failure(self, mock_convert):
        mock_convert.side_effect = Exception("PDF conversion error")

        pdf_bytes = b"invalid_pdf_data"

        service = PDFService()
        with pytest.raises(Exception) as exc_info:
            service.pdf_to_images(pdf_bytes)

        assert "Failed to convert PDF to images" in str(exc_info.value)
