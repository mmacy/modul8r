"""
Playwright End-to-End Tests with YAML Configuration

These tests use Playwright to launch browsers, navigate the web application,
upload PDFs, configure settings, and verify the complete PDF-to-Markdown
conversion workflow through the web UI using YAML-configured test profiles.
"""

import pytest
import pytest_asyncio
import asyncio
import os
import time
import json
from pathlib import Path
from playwright.async_api import async_playwright, Page, Browser, expect
import uvicorn
import threading
import requests

from src.modul8r.main import app
from .e2e_config import E2EConfig, E2EConfigError


def pytest_generate_tests(metafunc):
    """Generate tests dynamically from YAML profiles."""
    if "e2e_profile" in metafunc.fixturenames:
        try:
            config = E2EConfig()
            profiles = config.get_profiles()
            if profiles:
                metafunc.parametrize("e2e_profile", list(profiles.keys()), ids=list(profiles.keys()))
            else:
                pytest.skip("No E2E profiles configured")
        except E2EConfigError as e:
            pytest.skip(f"E2E configuration error: {e}")


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
def e2e_config():
    """Load and validate E2E configuration."""
    try:
        config = E2EConfig()
        return config
    except E2EConfigError as e:
        pytest.skip(f"E2E configuration error: {e}")


@pytest.fixture(scope="session")
def openai_api_key():
    """Check for OpenAI API key."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        pytest.skip("OPENAI_API_KEY environment variable not set - skipping E2E tests")
    return api_key


@pytest_asyncio.fixture(scope="session")
async def real_server(openai_api_key, e2e_config):
    """Start the real FastAPI server for Playwright browser automation."""
    server_settings = e2e_config.get_server_settings()
    server_port = server_settings["port"]
    server_url = f"http://127.0.0.1:{server_port}"

    # Start server in a separate thread with real services (no mocks)
    def run_server():
        uvicorn.run(app, host="127.0.0.1", port=server_port, log_level=server_settings["log_level"])

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Wait for server to start and be ready
    max_retries = server_settings["startup_timeout"]
    for i in range(max_retries):
        try:
            response = requests.get(f"{server_url}/status", timeout=5)
            if response.status_code == 200:
                print(f"E2E server ready after {i + 1} attempts on port {server_port}")
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        pytest.fail(f"E2E server failed to start after {max_retries} seconds")

    yield server_url


@pytest_asyncio.fixture
async def browser(e2e_config):
    """Launch Playwright browser with YAML-configured settings."""
    browser_settings = e2e_config.get_browser_settings()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=browser_settings["headless"], slow_mo=browser_settings["slow_mo"])
        yield browser
        await browser.close()


@pytest_asyncio.fixture
async def page(browser: Browser, real_server, e2e_config):
    """Create browser page and navigate to application with YAML settings."""
    page = await browser.new_page()

    # Apply viewport and timeout settings from YAML
    browser_settings = e2e_config.get_browser_settings()
    page_settings = e2e_config.get_page_settings()

    await page.set_viewport_size(browser_settings["viewport"])
    page.set_default_timeout(browser_settings["timeout"])

    # Navigate to the web application
    await page.goto(real_server, timeout=page_settings["navigation_timeout"])
    yield page
    await page.close()


class TestE2EInfrastructure:
    """Test infrastructure components that support all E2E profiles."""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_page_loads_with_real_server(self, page: Page):
        """Test that the main page loads correctly with real server."""
        # Verify page loaded correctly
        await expect(page).to_have_title("modul8r - PDF to Markdown Converter")
        await expect(page.locator("h1")).to_have_text("modul8r")

        # Check that models dropdown gets populated (real OpenAI API call)
        model_select = page.locator('select[name="model"]')
        await page.wait_for_function(
            "document.querySelector('select[name=\"model\"]').options.length > 1", timeout=10000
        )

        # Verify we have real model options
        options = await model_select.locator("option").all_text_contents()
        print(f"Available models from OpenAI API: {options}")

        assert len(options) > 1, "Should have more than just placeholder"
        assert any("gpt" in option.lower() for option in options), "Should have real OpenAI models"

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_websocket_log_streaming(self, page: Page):
        """Test WebSocket log streaming through browser interface."""
        # Enable log viewer via Playwright checkbox interaction
        log_checkbox = page.locator('input[type="checkbox"]#showLogs')
        await log_checkbox.check()

        # Wait for log viewer to appear
        log_viewer = page.locator("#logViewer")
        await expect(log_viewer).to_be_visible()

        # Check WebSocket connection status
        connection_status = page.locator("#connectionStatus")
        await expect(connection_status).to_have_text("Connected")

        # Wait for log entries to appear
        await page.wait_for_timeout(2000)

        # Verify log entries are streaming
        log_entries = page.locator(".log-entry")
        log_count = await log_entries.count()

        print(f"WebSocket streaming: {log_count} log entries received")
        assert log_count > 0, "Expected to see log entries from WebSocket connection"

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_phase1_status_endpoint(self, page: Page):
        """Test Phase 1 status endpoint through browser navigation."""
        # Navigate to Phase 1 status endpoint
        await page.goto(f"{page.url}status/phase1")

        # Get JSON response content
        content = await page.text_content("pre")
        if not content:
            content = await page.text_content("body")

        # Parse and verify Phase 1 status structure
        status_data = json.loads(content)

        assert status_data["phase1_status"] == "active"
        assert "feature_flags" in status_data
        assert "safeguards" in status_data

        # Verify feature flags
        feature_flags = status_data["feature_flags"]
        assert feature_flags["message_throttling"] is True
        assert feature_flags["memory_management"] is True
        assert feature_flags["performance_monitoring"] is True

        print(f"Phase 1 status verified: {json.dumps(status_data, indent=2)}")


class TestE2EProfiles:
    """YAML-driven E2E tests using Playwright browser automation."""

    @pytest.mark.e2e
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_e2e_profile_browser_automation(self, page: Page, e2e_profile: str, e2e_config: E2EConfig):
        """Complete browser automation test using YAML profile configuration."""
        # Load profile configuration
        profile = e2e_config.get_profile(e2e_profile)
        print(f"Running E2E test for profile: {e2e_profile}")
        print(f"Profile config: {profile}")

        # Validate PDF file exists
        pdf_path = Path("playwright-e2e") / profile["pdf_file"]
        if not pdf_path.exists():
            pytest.skip(f"PDF file not found for profile '{e2e_profile}': {pdf_path}")

        # === PLAYWRIGHT BROWSER AUTOMATION BEGINS ===

        # 1. Verify page loaded correctly
        await expect(page).to_have_title("modul8r - PDF to Markdown Converter")
        await expect(page.locator("h1")).to_have_text("modul8r")

        # 2. Enable log viewer (Playwright checkbox interaction)
        log_checkbox = page.locator('input[type="checkbox"]#showLogs')
        await log_checkbox.check()
        await expect(page.locator("#logViewer")).to_be_visible()

        # 3. Wait for models to load via AJAX (Playwright waits for dynamic content)
        model_select = page.locator('select[name="model"]')
        await page.wait_for_function(
            "document.querySelector('select[name=\"model\"]').options.length > 1", timeout=10000
        )

        # 4. Select model from YAML profile (NO hardcoded fallbacks - use exact model)
        available_models = await model_select.locator("option").all_text_contents()
        if profile["model"] not in available_models:
            pytest.fail(f"Model '{profile['model']}' not available. Available models: {available_models}")

        await model_select.select_option(profile["model"])
        print(f"Selected model: {profile['model']}")

        # 5. Configure detail level (Playwright dropdown interaction)
        detail_select = page.locator('select[name="detail"]')
        await detail_select.select_option(profile["detail_level"])
        print(f"Set detail level: {profile['detail_level']}")

        # 6. Set concurrency via slider (Playwright slider manipulation)
        concurrency_slider = page.locator('input[type="range"]#concurrency')
        await concurrency_slider.fill(str(profile["concurrency"]))

        # Verify slider value display updated
        concurrency_display = page.locator("#concurrencyValue")
        await expect(concurrency_display).to_have_text(str(profile["concurrency"]))
        print(f"Set concurrency: {profile['concurrency']}")

        # 7. Upload PDF file (Playwright file upload)
        file_input = page.locator('input[type="file"]#files')
        await file_input.set_input_files(str(pdf_path))
        print(f"Uploaded PDF: {pdf_path}")

        # 8. Submit form and monitor loading state (Playwright form submission)
        convert_button = page.locator('button[type="submit"]#convertBtn')
        await convert_button.click()

        # Verify loading state via Playwright element state checking
        await expect(convert_button).to_have_text("Converting...")
        await expect(convert_button).to_be_disabled()
        print("Form submitted, conversion started")

        # 9. Monitor WebSocket logs in real-time (Playwright WebSocket interaction)
        log_content = page.locator("#logContent")
        connection_status = page.locator("#connectionStatus")
        await expect(connection_status).to_have_text("Connected")

        # Wait for processing logs to appear
        await page.wait_for_function("document.querySelector('#logContent').children.length > 0", timeout=30000)
        print("Processing logs visible in browser")

        # 10. Wait for conversion completion (Playwright waits for UI state change)
        timeout_ms = profile["timeout_minutes"] * 60 * 1000
        print(f"Waiting up to {profile['timeout_minutes']} minutes for completion...")

        await expect(page.locator("#outputArea")).to_be_visible(timeout=timeout_ms)
        await expect(convert_button).to_have_text("Convert", timeout=timeout_ms)
        await expect(convert_button).not_to_be_disabled()
        print("Conversion completed successfully")

        # 11. Verify results in browser (Playwright content verification)
        results_div = page.locator("#results")
        await expect(results_div).to_be_visible()

        file_results = page.locator(".file-result")
        file_count = await file_results.count()
        assert file_count >= 1, "Expected at least one conversion result"
        print(f"Found {file_count} conversion results")

        # 12. Verify result content structure (Playwright text content extraction)
        first_result = file_results.first
        result_header = first_result.locator("h3")
        header_text = await result_header.text_content()
        assert profile["pdf_file"] in header_text, f"Expected filename '{profile['pdf_file']}' in header"

        # 13. Test download functionality (Playwright download handling)
        download_button = first_result.locator(".download-btn")
        await expect(download_button).to_be_visible()

        # Playwright download event handling
        async with page.expect_download() as download_info:
            await download_button.click()
        download = await download_info.value

        # Verify download properties
        expected_filename = profile["pdf_file"].replace(".pdf", ".md")
        assert download.suggested_filename == expected_filename
        print(f"Download test successful: {download.suggested_filename}")

        # 14. Validate converted content (Playwright content extraction and validation)
        markdown_content = first_result.locator(".markdown-content")
        content_text = await markdown_content.text_content()

        # Generic content validation (no model-specific expectations)
        assert len(content_text) > 100, "Converted content should be substantial"
        assert not content_text.startswith("Error"), "Content should not be an error message"

        print(f"Content validation passed: {len(content_text)} characters converted")
        print(f"Profile '{e2e_profile}' test completed successfully!")

        # === PLAYWRIGHT BROWSER AUTOMATION ENDS ===

    @pytest.mark.e2e
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_e2e_profile_concurrent_processing(self, page: Page, e2e_profile: str, e2e_config: E2EConfig):
        """Test concurrent processing UI controls for E2E profile."""
        profile = e2e_config.get_profile(e2e_profile)
        pdf_path = Path("playwright-e2e") / profile["pdf_file"]

        if not pdf_path.exists():
            pytest.skip(f"PDF file not found: {pdf_path}")

        # Enable logs to monitor concurrent processing
        await page.locator('input[type="checkbox"]#showLogs').check()

        # Set concurrency from profile
        concurrency_slider = page.locator('input[type="range"]#concurrency')
        await concurrency_slider.fill(str(profile["concurrency"]))

        # Verify the slider value is displayed
        concurrency_value = page.locator("#concurrencyValue")
        await expect(concurrency_value).to_have_text(str(profile["concurrency"]))

        # Wait for models and select the one from profile
        model_select = page.locator('select[name="model"]')
        await page.wait_for_function(
            "document.querySelector('select[name=\"model\"]').options.length > 1", timeout=10000
        )
        await model_select.select_option(profile["model"])

        # Upload file and start processing
        await page.locator('input[type="file"]#files').set_input_files(str(pdf_path))

        convert_button = page.locator('button[type="submit"]#convertBtn')
        await convert_button.click()

        # Monitor logs for concurrent processing indicators
        log_content = page.locator("#logContent")
        await page.wait_for_timeout(3000)  # Wait for processing to start

        # Check concurrent processing in logs
        log_text = await log_content.text_content()
        print(f"Concurrent processing logs for {profile['concurrency']} threads:")
        print(log_text[-1000:])  # Last 1000 characters

        # Wait for completion
        timeout_ms = profile["timeout_minutes"] * 60 * 1000
        await expect(page.locator("#outputArea")).to_be_visible(timeout=timeout_ms)
        await expect(convert_button).to_have_text("Convert", timeout=timeout_ms)

        # Verify successful results despite high concurrency
        file_results = page.locator(".file-result")
        file_count = await file_results.count()
        assert file_count >= 1, f"Concurrent processing with {profile['concurrency']} threads should produce results"

        print(f"Concurrent processing test passed for {profile['concurrency']} threads")

    @pytest.mark.e2e
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_e2e_profile_download_functionality(self, page: Page, e2e_profile: str, e2e_config: E2EConfig):
        """Test download functionality for E2E profile."""
        profile = e2e_config.get_profile(e2e_profile)
        pdf_path = Path("playwright-e2e") / profile["pdf_file"]

        if not pdf_path.exists():
            pytest.skip(f"PDF file not found: {pdf_path}")

        # Quick setup for download test
        await page.locator('input[type="checkbox"]#showLogs').check()

        # Configure from profile
        model_select = page.locator('select[name="model"]')
        await page.wait_for_function(
            "document.querySelector('select[name=\"model\"]').options.length > 1", timeout=10000
        )
        await model_select.select_option(profile["model"])
        await page.locator('select[name="detail"]').select_option(profile["detail_level"])

        # Use lower concurrency for faster test
        await page.locator('input[type="range"]#concurrency').fill("1")

        # Upload and convert
        await page.locator('input[type="file"]#files').set_input_files(str(pdf_path))
        await page.locator('button[type="submit"]#convertBtn').click()

        # Wait for completion
        timeout_ms = profile["timeout_minutes"] * 60 * 1000
        await expect(page.locator("#outputArea")).to_be_visible(timeout=timeout_ms)
        await expect(page.locator('button[type="submit"]#convertBtn')).to_have_text("Convert", timeout=timeout_ms)

        # Test download functionality
        download_button = page.locator(".download-btn").first
        await expect(download_button).to_be_visible()

        # Handle download
        async with page.expect_download() as download_info:
            await download_button.click()
        download = await download_info.value

        # Verify download properties
        expected_filename = profile["pdf_file"].replace(".pdf", ".md")
        assert download.suggested_filename == expected_filename

        # Save and verify downloaded file
        download_path = f"/tmp/{download.suggested_filename}"
        await download.save_as(download_path)

        assert os.path.exists(download_path)

        with open(download_path, "r", encoding="utf-8") as f:
            downloaded_content = f.read()

        assert len(downloaded_content) > 100, "Downloaded file should have substantial content"
        print(f"Download test passed: {len(downloaded_content)} characters saved to {download_path}")

        # Clean up
        os.remove(download_path)


# Pytest configuration
def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "e2e: marks tests as end-to-end browser automation tests")
    config.addinivalue_line("markers", "slow: marks tests as slow (may take several minutes)")


def pytest_collection_modifyitems(config, items):
    """Automatically mark E2E tests as slow."""
    for item in items:
        if "e2e" in item.name.lower() or "E2E" in str(item.cls):
            item.add_marker(pytest.mark.slow)
        if "test_e2e_profile" in item.name:
            item.add_marker(pytest.mark.e2e)
