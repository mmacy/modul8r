"""
End-to-end tests using real RPG adventure modules.
Tests the complete PDF-to-Markdown conversion pipeline with actual files.
"""

import pytest
import asyncio
import os
import time
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser, expect
from fastapi.testclient import TestClient
import uvicorn
import threading
import json

from src.modul8r.main import app


# Test configuration
TEST_MODULE_DIR = Path("/Users/mmacy/Documents/bx_adventure_modules_basic/B1_-_B12")
TEST_MODULE_FILE = "B01_-_In_Search_of_the_Unknown.pdf"  # Start with the first module
SERVER_PORT = 8002  # Use different port to avoid conflicts
SERVER_URL = f"http://127.0.0.1:{SERVER_PORT}"


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def test_pdf_path():
    """Get the path to the test PDF module."""
    pdf_path = TEST_MODULE_DIR / TEST_MODULE_FILE
    if not pdf_path.exists():
        pytest.skip(f"Test PDF not found: {pdf_path}")
    return pdf_path


@pytest.fixture(scope="session")
def openai_api_key():
    """Check for OpenAI API key."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY environment variable not set - skipping real module tests")
    return api_key


@pytest.fixture(scope="session")
async def real_server(openai_api_key):
    """Start the real FastAPI server for end-to-end testing."""
    # Start server in a separate thread with real services
    def run_server():
        uvicorn.run(
            app, 
            host="127.0.0.1", 
            port=SERVER_PORT, 
            log_level="info"  # Use info level to see what's happening
        )
    
    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()
    
    # Wait for server to start and be ready
    max_retries = 30
    for i in range(max_retries):
        try:
            # Try to connect to the server
            import requests
            response = requests.get(f"{SERVER_URL}/status", timeout=5)
            if response.status_code == 200:
                print(f"Server ready after {i + 1} attempts")
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        pytest.fail(f"Server failed to start after {max_retries} seconds")
    
    yield SERVER_URL


@pytest.fixture
async def browser():
    """Create a browser instance."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # Set to False to see what's happening during development
            slow_mo=500      # Slow down actions for better visibility
        )
        yield browser
        await browser.close()


@pytest.fixture
async def page(browser: Browser, real_server):
    """Create a page instance and navigate to the application."""
    page = await browser.new_page()
    
    # Set longer timeout for real operations
    page.set_default_timeout(60000)  # 60 seconds
    
    await page.goto(real_server)
    yield page
    await page.close()


class TestRealModuleConversion:
    """Test actual PDF-to-Markdown conversion using real RPG modules."""
    
    @pytest.mark.asyncio
    @pytest.mark.slow  # Mark as slow test
    async def test_page_loads_with_real_server(self, page: Page):
        """Test that the main page loads correctly with real server."""
        # Check title
        await expect(page).to_have_title("modul8r - PDF to Markdown Converter")
        
        # Check main heading
        heading = page.locator("h1")
        await expect(heading).to_have_text("modul8r")
        
        # Check that models dropdown gets populated (real API call)
        model_select = page.locator('select[name="model"]')
        
        # Wait for models to load from real OpenAI API
        await page.wait_for_function(
            "document.querySelector('select[name=\"model\"]').options.length > 1",
            timeout=10000
        )
        
        # Verify we have real model options
        options = await model_select.locator("option").all_text_contents()
        print(f"Available models: {options}")
        
        # Should have more than just the placeholder
        assert len(options) > 1
        # Should have real OpenAI models
        assert any("gpt" in option.lower() for option in options)
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_phase1_status_endpoint(self, page: Page):
        """Test that Phase 1 status endpoint works correctly."""
        # Navigate to the Phase 1 status endpoint
        await page.goto(f"{page.url}status/phase1")
        
        # Should return JSON with Phase 1 status
        content = await page.text_content("pre")  # JSON is often wrapped in <pre>
        if not content:
            content = await page.text_content("body")
        
        # Parse JSON response
        status_data = json.loads(content)
        
        # Verify Phase 1 status structure
        assert status_data["phase1_status"] == "active"
        assert "feature_flags" in status_data
        assert "safeguards" in status_data
        
        # Check feature flags
        feature_flags = status_data["feature_flags"]
        assert feature_flags["message_throttling"] is True
        assert feature_flags["memory_management"] is True
        assert feature_flags["performance_monitoring"] is True
        
        # Check safeguards
        safeguards = status_data["safeguards"]
        assert "message_throttling" in safeguards
        assert "memory_management" in safeguards
        assert "performance_monitoring" in safeguards
        
        print(f"Phase 1 status: {json.dumps(status_data, indent=2)}")
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_websocket_log_streaming(self, page: Page):
        """Test that WebSocket log streaming works with real server."""
        # Enable log viewer
        log_checkbox = page.locator('input[type="checkbox"]#showLogs')
        await log_checkbox.check()
        
        # Wait for log viewer to appear
        log_viewer = page.locator("#logViewer")
        await expect(log_viewer).to_be_visible()
        
        # Check connection status
        connection_status = page.locator("#connectionStatus")
        await expect(connection_status).to_have_text("Connected")
        
        # Wait a moment for some log entries to appear
        await page.wait_for_timeout(2000)
        
        # Check that we have some log entries
        log_entries = page.locator(".log-entry")
        log_count = await log_entries.count()
        
        print(f"Found {log_count} log entries")
        assert log_count > 0, "Expected to see some log entries from WebSocket connection"
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_real_module_conversion_b01(self, page: Page, test_pdf_path):
        """Test converting the B01 module (In Search of the Unknown) to Markdown."""
        print(f"Testing conversion of: {test_pdf_path}")
        
        # Enable log viewer to see progress
        log_checkbox = page.locator('input[type="checkbox"]#showLogs')
        await log_checkbox.check()
        
        # Wait for log viewer to appear
        await expect(page.locator("#logViewer")).to_be_visible()
        
        # Select a fast model for testing (to avoid long waits)
        model_select = page.locator('select[name="model"]')
        await model_select.wait_for()
        
        # Wait for models to be populated and select a suitable one
        await page.wait_for_function(
            "document.querySelector('select[name=\"model\"]').options.length > 1",
            timeout=10000
        )
        
        # Try to select gpt-4o-mini if available (faster and cheaper)
        model_options = await model_select.locator("option").all_text_contents()
        print(f"Available models: {model_options}")
        
        if "gpt-4o-mini" in model_options:
            await model_select.select_option("gpt-4o-mini")
        elif any("gpt-4o" in option for option in model_options):
            # Select any gpt-4o variant
            for option in model_options:
                if "gpt-4o" in option and "mini" not in option:
                    await model_select.select_option(option)
                    break
        
        # Set detail level to low for faster processing
        detail_select = page.locator('select[name="detail"]')
        await detail_select.select_option("low")
        
        # Set concurrency to 1 for controlled testing
        concurrency_slider = page.locator('input[type="range"]#concurrency')
        await concurrency_slider.fill("1")
        
        # Upload the test PDF file
        file_input = page.locator('input[type="file"]#files')
        await file_input.set_input_files(str(test_pdf_path))
        
        # Submit the form
        convert_button = page.locator('button[type="submit"]#convertBtn')
        await convert_button.click()
        
        # Verify loading state
        await expect(convert_button).to_have_text("Converting...")
        await expect(convert_button).to_be_disabled()
        
        # Wait for output area to appear
        output_area = page.locator("#outputArea")
        await expect(output_area).to_be_visible(timeout=120000)  # 2 minutes max
        
        # Wait for conversion to complete (button text changes back)
        await expect(convert_button).to_have_text("Convert", timeout=300000)  # 5 minutes max
        await expect(convert_button).not_to_be_disabled()
        
        # Check that we have results
        results_div = page.locator("#results")
        await expect(results_div).to_be_visible()
        
        # Should have at least one file result
        file_results = page.locator(".file-result")
        file_count = await file_results.count()
        assert file_count >= 1, "Expected at least one file result"
        
        # Check the first result
        first_result = file_results.first
        await expect(first_result).to_be_visible()
        
        # Should have the filename as header
        result_header = first_result.locator("h3")
        header_text = await result_header.text_content()
        assert TEST_MODULE_FILE in header_text
        
        # Should have a download button
        download_button = first_result.locator(".download-btn")
        await expect(download_button).to_be_visible()
        await expect(download_button).to_have_text("⬇️ Download")
        
        # Should have markdown content
        markdown_content = first_result.locator(".markdown-content")
        await expect(markdown_content).to_be_visible()
        
        # Get the actual converted content
        content_text = await markdown_content.text_content()
        print(f"Converted content length: {len(content_text)} characters")
        print(f"Content preview: {content_text[:500]}...")
        
        # Basic validation of markdown content
        assert len(content_text) > 100, "Converted content should be substantial"
        assert not content_text.startswith("Error"), "Content should not be an error message"
        
        # Should contain typical RPG module elements
        content_lower = content_text.lower()
        rpg_keywords = ["dungeon", "adventure", "character", "monster", "treasure", "room", "level"]
        found_keywords = [keyword for keyword in rpg_keywords if keyword in content_lower]
        print(f"Found RPG keywords: {found_keywords}")
        
        # Should find at least some RPG-related content
        assert len(found_keywords) > 0, f"Expected to find RPG-related keywords, got: {found_keywords}"
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_download_functionality(self, page: Page, test_pdf_path):
        """Test the download functionality with a real converted module."""
        # This test assumes the previous test has run and we have results
        # In a real test suite, you might want to combine or set up state differently
        
        # Quick conversion setup (similar to previous test but faster)
        await page.locator('input[type="checkbox"]#showLogs').check()
        
        # Wait for models and select fast one
        model_select = page.locator('select[name="model"]')
        await page.wait_for_function(
            "document.querySelector('select[name=\"model\"]').options.length > 1",
            timeout=10000
        )
        
        # Select fastest model and lowest detail
        model_options = await model_select.locator("option").all_text_contents()
        if "gpt-4o-mini" in model_options:
            await model_select.select_option("gpt-4o-mini")
        
        await page.locator('select[name="detail"]').select_option("low")
        await page.locator('input[type="range"]#concurrency').fill("1")
        
        # Upload and convert
        await page.locator('input[type="file"]#files').set_input_files(str(test_pdf_path))
        await page.locator('button[type="submit"]#convertBtn').click()
        
        # Wait for completion
        await expect(page.locator("#outputArea")).to_be_visible(timeout=120000)
        await expect(page.locator('button[type="submit"]#convertBtn')).to_have_text("Convert", timeout=300000)
        
        # Test download functionality
        download_button = page.locator(".download-btn").first
        await expect(download_button).to_be_visible()
        
        # Start waiting for download before clicking
        async with page.expect_download() as download_info:
            await download_button.click()
        download = await download_info.value
        
        # Verify download properties
        suggested_filename = download.suggested_filename
        print(f"Downloaded file: {suggested_filename}")
        
        # Should be a .md file with the same base name as the PDF
        expected_filename = TEST_MODULE_FILE.replace(".pdf", ".md")
        assert suggested_filename == expected_filename
        
        # Save and check the downloaded file
        download_path = f"/tmp/{suggested_filename}"
        await download.save_as(download_path)
        
        # Verify the downloaded file exists and has content
        assert os.path.exists(download_path)
        
        with open(download_path, 'r', encoding='utf-8') as f:
            downloaded_content = f.read()
        
        print(f"Downloaded content length: {len(downloaded_content)} characters")
        assert len(downloaded_content) > 100, "Downloaded file should have substantial content"
        
        # Clean up
        os.remove(download_path)
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_concurrent_processing_with_real_module(self, page: Page, test_pdf_path):
        """Test concurrent processing settings with a real module."""
        # Enable logs to monitor concurrent processing
        await page.locator('input[type="checkbox"]#showLogs').check()
        
        # Set higher concurrency for this test
        concurrency_slider = page.locator('input[type="range"]#concurrency')
        await concurrency_slider.fill("3")  # Test with 3 concurrent requests
        
        # Verify the slider value is displayed
        concurrency_value = page.locator("#concurrencyValue")
        await expect(concurrency_value).to_have_text("3")
        
        # Select model and upload file
        model_select = page.locator('select[name="model"]')
        await page.wait_for_function(
            "document.querySelector('select[name=\"model\"]').options.length > 1",
            timeout=10000
        )
        
        model_options = await model_select.locator("option").all_text_contents()
        if "gpt-4o-mini" in model_options:
            await model_select.select_option("gpt-4o-mini")
        
        await page.locator('input[type="file"]#files').set_input_files(str(test_pdf_path))
        
        # Start conversion
        convert_button = page.locator('button[type="submit"]#convertBtn')
        await convert_button.click()
        
        # Monitor logs for concurrent processing indicators
        log_content = page.locator("#logContent")
        
        # Wait a bit for processing to start
        await page.wait_for_timeout(3000)
        
        # Check that we can see concurrent processing in logs
        # Look for multiple "Processing page" entries happening close together
        log_text = await log_content.text_content()
        print("Log content during concurrent processing:")
        print(log_text[-1000:])  # Last 1000 characters
        
        # Wait for completion
        await expect(page.locator("#outputArea")).to_be_visible(timeout=180000)
        await expect(convert_button).to_have_text("Convert", timeout=300000)
        
        # Should still have successful results with concurrent processing
        file_results = page.locator(".file-result")
        file_count = await file_results.count()
        assert file_count >= 1, "Concurrent processing should still produce results"
    
    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_phase1_safeguards_during_conversion(self, page: Page, test_pdf_path):
        """Test that Phase 1 safeguards are working during real conversion."""
        # Enable logs to monitor safeguards
        await page.locator('input[type="checkbox"]#showLogs').check()
        
        # Start a conversion to trigger the safeguards
        model_select = page.locator('select[name="model"]')
        await page.wait_for_function(
            "document.querySelector('select[name=\"model\"]').options.length > 1",
            timeout=10000
        )
        
        model_options = await model_select.locator("option").all_text_contents()
        if "gpt-4o-mini" in model_options:
            await model_select.select_option("gpt-4o-mini")
        
        await page.locator('input[type="file"]#files').set_input_files(str(test_pdf_path))
        await page.locator('button[type="submit"]#convertBtn').click()
        
        # Let it run for a while to generate activity
        await page.wait_for_timeout(10000)  # 10 seconds
        
        # Check Phase 1 status during processing
        # Open new tab to check status without interrupting conversion
        new_page = await page.context.new_page()
        await new_page.goto(f"{SERVER_URL}/status/phase1")
        
        # Get status
        content = await new_page.text_content("body")
        status_data = json.loads(content)
        
        print("Phase 1 status during conversion:")
        print(json.dumps(status_data, indent=2))
        
        # Verify safeguards are active
        safeguards = status_data["safeguards"]
        
        # Message throttling should be active
        throttling = safeguards["message_throttling"]
        assert throttling["status"] == "active"
        
        # Memory management should be active
        memory = safeguards["memory_management"]
        assert memory["status"] == "active"
        assert memory["entries_count"] >= 0
        
        # Performance monitoring should be active
        perf = safeguards["performance_monitoring"]
        assert perf["status"] == "active"
        
        # Should have at least one active connection
        assert status_data["active_connections"] >= 1
        
        await new_page.close()
        
        # Let original conversion complete
        await expect(page.locator("#outputArea")).to_be_visible(timeout=300000)
        
        print("Phase 1 safeguards test completed successfully!")


# Utility functions for test setup
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "slow: marks tests as slow (may take several minutes)"
    )


def pytest_collection_modifyitems(config, items):
    """Automatically mark tests that use real modules as slow."""
    for item in items:
        if "real_module" in item.name or "Real" in str(item.cls):
            item.add_marker(pytest.mark.slow)