import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, Mock, AsyncMock
from io import BytesIO

from src.modul8r.main import app, get_openai_service, get_pdf_service
from src.modul8r.services import OpenAIService, PDFService


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def mock_openai_service():
    service = Mock(spec=OpenAIService)
    service.get_vision_models = AsyncMock(return_value=["gpt-4o", "gpt-4o-mini"])
    service.process_images_batch = AsyncMock(return_value=["# Test Content"])
    return service


@pytest.fixture
def mock_pdf_service():
    service = Mock(spec=PDFService)
    service.pdf_to_images.return_value = [b"fake_image_data"]
    service.images_to_base64.return_value = ["base64_encoded_image"]
    return service


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

    def test_get_models_success(self, client, mock_openai_service):
        # Override the dependency
        app.dependency_overrides[get_openai_service] = lambda: mock_openai_service
        
        try:
            response = client.get("/models")
            assert response.status_code == 200
            assert response.json() == ["gpt-4o", "gpt-4o-mini"]
        finally:
            # Clean up
            app.dependency_overrides.clear()

    def test_get_models_failure(self, client, mock_openai_service):
        # Clear cache to ensure fresh error is triggered
        from src.modul8r.model_cache import model_cache
        model_cache.clear_cache()
        
        # Configure service to raise exception
        mock_openai_service.get_vision_models = AsyncMock(side_effect=Exception("API Error"))
        
        # Override the dependency
        app.dependency_overrides[get_openai_service] = lambda: mock_openai_service
        
        try:
            response = client.get("/models")
            assert response.status_code == 500
            assert "Failed to fetch models" in response.json()["detail"]
        finally:
            # Clean up
            app.dependency_overrides.clear()

    def test_convert_no_files(self, client):
        response = client.post("/convert")
        assert response.status_code == 422  # Unprocessable Entity

    def test_convert_pdfs_success(self, client, mock_openai_service, mock_pdf_service, sample_pdf_file):
        # Configure services
        mock_openai_service.get_vision_models = AsyncMock(return_value=["gpt-4o"])
        
        # Override dependencies
        app.dependency_overrides[get_openai_service] = lambda: mock_openai_service
        app.dependency_overrides[get_pdf_service] = lambda: mock_pdf_service
        
        try:
            # Prepare file upload
            files = {"files": ("test.pdf", sample_pdf_file.getvalue(), "application/pdf")}
            data = {"model": "gpt-4o", "detail": "high"}

            response = client.post("/convert", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            assert "test.pdf" in result
            assert result["test.pdf"] == "# Test Content"
        finally:
            # Clean up
            app.dependency_overrides.clear()

    def test_convert_pdfs_processing_error(self, client, mock_openai_service, mock_pdf_service, sample_pdf_file):
        # Configure services with error
        mock_openai_service.get_vision_models = AsyncMock(return_value=["gpt-4o"])
        mock_pdf_service.pdf_to_images.side_effect = Exception("PDF processing error")
        
        # Override dependencies
        app.dependency_overrides[get_openai_service] = lambda: mock_openai_service
        app.dependency_overrides[get_pdf_service] = lambda: mock_pdf_service
        
        try:
            # Prepare file upload
            files = {"files": ("test.pdf", sample_pdf_file.getvalue(), "application/pdf")}
            data = {"model": "gpt-4o", "detail": "high"}

            response = client.post("/convert", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            assert "test.pdf" in result
            assert "Error processing test.pdf" in result["test.pdf"]
        finally:
            # Clean up
            app.dependency_overrides.clear()

    def test_convert_pdfs_no_model_specified(self, client, mock_openai_service, mock_pdf_service, sample_pdf_file):
        # Configure services
        mock_openai_service.get_vision_models = AsyncMock(return_value=["gpt-4o"])
        
        # Override dependencies
        app.dependency_overrides[get_openai_service] = lambda: mock_openai_service
        app.dependency_overrides[get_pdf_service] = lambda: mock_pdf_service
        
        try:
            # Prepare file upload without model specified
            files = {"files": ("test.pdf", sample_pdf_file.getvalue(), "application/pdf")}
            data = {"detail": "high"}

            response = client.post("/convert", files=files, data=data)

            assert response.status_code == 200
            # Should have called get_vision_models to get default model
            mock_openai_service.get_vision_models.assert_called()
        finally:
            # Clean up
            app.dependency_overrides.clear()

    def test_convert_non_pdf_file(self, client):
        # Test with non-PDF file
        files = {"files": ("test.txt", b"Some text content", "text/plain")}
        data = {"model": "gpt-4o", "detail": "high"}

        response = client.post("/convert", files=files, data=data)

        assert response.status_code == 200
        result = response.json()
        # Should return empty result since no PDF files were processed
        assert result == {}

    def test_convert_multiple_pages(self, client, mock_openai_service, mock_pdf_service, sample_pdf_file):
        # Configure services for multiple pages
        mock_openai_service.get_vision_models = AsyncMock(return_value=["gpt-4o"])
        mock_openai_service.process_images_batch = AsyncMock(return_value=["# Page 1", "# Page 2"])
        mock_pdf_service.pdf_to_images.return_value = [b"page1_data", b"page2_data"]
        mock_pdf_service.images_to_base64.return_value = ["page1_base64", "page2_base64"]
        
        # Override dependencies
        app.dependency_overrides[get_openai_service] = lambda: mock_openai_service
        app.dependency_overrides[get_pdf_service] = lambda: mock_pdf_service
        
        try:
            # Prepare file upload
            files = {"files": ("test.pdf", sample_pdf_file.getvalue(), "application/pdf")}
            data = {"model": "gpt-4o", "detail": "high"}

            response = client.post("/convert", files=files, data=data)

            assert response.status_code == 200
            result = response.json()
            assert "test.pdf" in result
            # Should combine pages with double line breaks (no horizontal rules)
            assert result["test.pdf"] == "# Page 1\n\n# Page 2"
        finally:
            # Clean up
            app.dependency_overrides.clear()
