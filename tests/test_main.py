import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock
from io import BytesIO

from src.modul8r.main import app


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def sample_pdf_file():
    """Create a simple PDF-like file for testing."""
    pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    return BytesIO(pdf_content)


class TestMainEndpoints:
    def test_root_endpoint(self, client):
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        assert "modul8r" in response.text

    @patch("src.modul8r.main.openai_service")
    def test_get_models_success(self, mock_service, client):
        mock_service.get_vision_models = AsyncMock(return_value=["gpt-4o", "gpt-4o-mini"])

        response = client.get("/models")
        assert response.status_code == 200
        assert response.json() == ["gpt-4o", "gpt-4o-mini"]

    @patch("src.modul8r.main.openai_service")
    def test_get_models_failure(self, mock_service, client):
        mock_service.get_vision_models = AsyncMock(side_effect=Exception("API Error"))

        response = client.get("/models")
        assert response.status_code == 500
        assert "Failed to fetch models" in response.json()["detail"]

    def test_convert_no_files(self, client):
        response = client.post("/convert")
        assert response.status_code == 422  # Unprocessable Entity

    @patch("src.modul8r.main.openai_service")
    @patch("src.modul8r.main.pdf_service")
    def test_convert_pdfs_success(self, mock_pdf_service, mock_openai_service, client, sample_pdf_file):
        # Mock services
        mock_openai_service.get_vision_models = AsyncMock(return_value=["gpt-4o"])
        mock_openai_service.process_image = AsyncMock(return_value="# Test Content")
        mock_pdf_service.pdf_to_images.return_value = [b"fake_image_data"]
        mock_pdf_service.images_to_base64.return_value = ["base64_encoded_image"]

        # Prepare file upload
        files = {"files": ("test.pdf", sample_pdf_file.getvalue(), "application/pdf")}
        data = {"model": "gpt-4o", "detail": "high"}

        response = client.post("/convert", files=files, data=data)

        assert response.status_code == 200
        result = response.json()
        assert "test.pdf" in result
        assert result["test.pdf"] == "# Test Content"

    @patch("src.modul8r.main.openai_service")
    @patch("src.modul8r.main.pdf_service")
    def test_convert_pdfs_processing_error(self, mock_pdf_service, mock_openai_service, client, sample_pdf_file):
        # Mock services with error
        mock_openai_service.get_vision_models = AsyncMock(return_value=["gpt-4o"])
        mock_pdf_service.pdf_to_images.side_effect = Exception("PDF processing error")

        # Prepare file upload
        files = {"files": ("test.pdf", sample_pdf_file.getvalue(), "application/pdf")}
        data = {"model": "gpt-4o", "detail": "high"}

        response = client.post("/convert", files=files, data=data)

        assert response.status_code == 200
        result = response.json()
        assert "test.pdf" in result
        assert "Error processing test.pdf" in result["test.pdf"]

    @patch("src.modul8r.main.openai_service")
    def test_convert_pdfs_no_model_specified(self, mock_openai_service, client, sample_pdf_file):
        # Mock service to return default model
        mock_openai_service.get_vision_models = AsyncMock(return_value=["gpt-4o"])

        with patch("src.modul8r.main.pdf_service") as mock_pdf_service:
            mock_pdf_service.pdf_to_images.return_value = [b"fake_image_data"]
            mock_pdf_service.images_to_base64.return_value = ["base64_encoded_image"]
            mock_openai_service.process_image = AsyncMock(return_value="# Test Content")

            # Prepare file upload without model specified
            files = {"files": ("test.pdf", sample_pdf_file.getvalue(), "application/pdf")}
            data = {"detail": "high"}

            response = client.post("/convert", files=files, data=data)

            assert response.status_code == 200
            # Should have called get_vision_models to get default model
            mock_openai_service.get_vision_models.assert_called()

    def test_convert_non_pdf_file(self, client):
        # Test with non-PDF file
        files = {"files": ("test.txt", b"Some text content", "text/plain")}
        data = {"model": "gpt-4o", "detail": "high"}

        response = client.post("/convert", files=files, data=data)

        assert response.status_code == 200
        result = response.json()
        # Should return empty result since no PDF files were processed
        assert result == {}

    @patch("src.modul8r.main.openai_service")
    @patch("src.modul8r.main.pdf_service")
    def test_convert_multiple_pages(self, mock_pdf_service, mock_openai_service, client, sample_pdf_file):
        # Mock services for multiple pages
        mock_openai_service.get_vision_models = AsyncMock(return_value=["gpt-4o"])
        mock_openai_service.process_image = AsyncMock(side_effect=["# Page 1", "# Page 2"])
        mock_pdf_service.pdf_to_images.return_value = [b"page1_data", b"page2_data"]
        mock_pdf_service.images_to_base64.return_value = ["page1_base64", "page2_base64"]

        # Prepare file upload
        files = {"files": ("test.pdf", sample_pdf_file.getvalue(), "application/pdf")}
        data = {"model": "gpt-4o", "detail": "high"}

        response = client.post("/convert", files=files, data=data)

        assert response.status_code == 200
        result = response.json()
        assert "test.pdf" in result
        # Should combine pages with horizontal rule
        assert result["test.pdf"] == "# Page 1\n\n# Page 2"
