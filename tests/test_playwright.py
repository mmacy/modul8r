import pytest
from playwright.async_api import async_playwright, Page, Browser
from fastapi.testclient import TestClient
import asyncio
import threading
import uvicorn
import time
from unittest.mock import patch, AsyncMock

from src.modul8r.main import app


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def server():
    """Start the FastAPI server for testing."""
    # Mock the services to avoid requiring real API keys
    with patch("src.modul8r.main.openai_service") as mock_openai:
        mock_openai.get_vision_models = AsyncMock(return_value=["gpt-4o", "gpt-4o-mini"])
        mock_openai.process_image = AsyncMock(return_value="# Test Document\n\nThis is a test conversion.")

        with patch("src.modul8r.main.pdf_service") as mock_pdf:
            mock_pdf.pdf_to_images.return_value = [b"fake_image_data"]
            mock_pdf.images_to_base64.return_value = ["base64_encoded_image"]

            # Start server in a separate thread
            def run_server():
                uvicorn.run(app, host="127.0.0.1", port=8001, log_level="error")

            server_thread = threading.Thread(target=run_server, daemon=True)
            server_thread.start()

            # Wait for server to start
            time.sleep(2)

            yield "http://127.0.0.1:8001"


@pytest.fixture
async def browser():
    """Create a browser instance."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        yield browser
        await browser.close()


@pytest.fixture
async def page(browser: Browser):
    """Create a page instance."""
    page = await browser.new_page()
    yield page
    await page.close()


class TestWebUI:
    @pytest.mark.asyncio
    async def test_page_loads(self, page: Page, server):
        """Test that the main page loads correctly."""
        await page.goto(server)

        # Check title
        title = await page.title()
        assert "modul8r" in title

        # Check main heading
        heading = await page.locator("h1").text_content()
        assert "modul8r" in heading

        # Check form elements exist
        assert await page.locator('input[type="file"]').count() == 1
        assert await page.locator('select[name="model"]').count() == 1
        assert await page.locator('select[name="detail"]').count() == 1
        assert await page.locator('button[type="submit"]').count() == 1

    @pytest.mark.asyncio
    async def test_models_dropdown_populated(self, page: Page, server):
        """Test that the models dropdown is populated dynamically."""
        await page.goto(server)

        # Wait for models to load
        await page.wait_for_selector('select[name="model"] option[value="gpt-4o"]')

        # Check that models are loaded
        model_select = page.locator('select[name="model"]')
        options = await model_select.locator("option").all_text_contents()

        assert "gpt-4o" in options
        assert "gpt-4o-mini" in options

    @pytest.mark.asyncio
    async def test_form_labels_sentence_case(self, page: Page, server):
        """Test that all form labels use sentence case."""
        await page.goto(server)

        # Check file input label
        file_label = await page.locator('label[for="files"]').text_content()
        assert file_label == "Select PDF files:"

        # Check model label
        model_label = await page.locator('label[for="model"]').text_content()
        assert model_label == "Model:"

        # Check detail label
        detail_label = await page.locator('label[for="detail"]').text_content()
        assert detail_label == "Image detail level:"

        # Check button text
        button_text = await page.locator('button[type="submit"]').text_content()
        assert button_text == "Convert"

    @pytest.mark.asyncio
    async def test_detail_dropdown_defaults(self, page: Page, server):
        """Test that detail dropdown has correct options and default."""
        await page.goto(server)

        detail_select = page.locator('select[name="detail"]')

        # Check options
        options = await detail_select.locator("option").all_text_contents()
        assert "High" in options
        assert "Low" in options

        # Check default selection
        selected_value = await detail_select.input_value()
        assert selected_value == "high"

    @pytest.mark.asyncio
    async def test_file_upload_restrictions(self, page: Page, server):
        """Test that file input only accepts PDF files."""
        await page.goto(server)

        file_input = page.locator('input[type="file"]')

        # Check accept attribute
        accept_attr = await file_input.get_attribute("accept")
        assert accept_attr == ".pdf"

        # Check multiple attribute
        multiple_attr = await file_input.get_attribute("multiple")
        assert multiple_attr is not None

    @pytest.mark.asyncio
    async def test_form_submission_shows_loading(self, page: Page, server):
        """Test that form submission shows loading state."""
        await page.goto(server)

        # Wait for page to fully load
        await page.wait_for_load_state("networkidle")

        # Create a fake PDF file content
        fake_pdf_content = b"%PDF-1.4\nfake pdf content"

        # Set file input (this is tricky with Playwright, so we'll simulate the behavior)
        # In a real test, you'd upload an actual file
        await page.evaluate("""
            () => {
                const fileInput = document.getElementById('files');
                const dataTransfer = new DataTransfer();
                const file = new File(['fake pdf content'], 'test.pdf', {type: 'application/pdf'});
                dataTransfer.items.add(file);
                fileInput.files = dataTransfer.files;
            }
        """)

        # Submit form
        convert_button = page.locator('button[type="submit"]')
        await convert_button.click()

        # Check that button shows loading state
        button_text = await convert_button.text_content()
        assert button_text == "Converting..."

        # Check that button is disabled during processing
        is_disabled = await convert_button.is_disabled()
        assert is_disabled

    @pytest.mark.asyncio
    async def test_output_area_appears_after_submission(self, page: Page, server):
        """Test that output area appears after form submission."""
        await page.goto(server)
        await page.wait_for_load_state("networkidle")

        # Initially output area should be hidden
        output_area = page.locator("#outputArea")
        is_visible = await output_area.is_visible()
        assert not is_visible

        # Simulate file upload and form submission
        await page.evaluate("""
            () => {
                const fileInput = document.getElementById('files');
                const dataTransfer = new DataTransfer();
                const file = new File(['fake pdf content'], 'test.pdf', {type: 'application/pdf'});
                dataTransfer.items.add(file);
                fileInput.files = dataTransfer.files;
            }
        """)

        await page.locator('button[type="submit"]').click()

        # Wait for output area to appear
        await page.wait_for_selector("#outputArea", state="visible")

        # Check that output area is now visible
        is_visible = await output_area.is_visible()
        assert is_visible
