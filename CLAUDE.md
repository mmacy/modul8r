# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

modul8r is a personal-use web service that converts scanned tabletop RPG adventure module PDFs into Markdown format using OpenAI's vision models. The application features modern async architecture with concurrent processing, real-time logging, and robust error handling.

## Current Status: **Production Ready**

- ✅ **Core functionality complete** - PDF to Markdown conversion working
- ✅ **Modern async architecture** - Python 3.13 TaskGroup concurrency (1-100 concurrent requests)
- ✅ **Real-time monitoring** - WebSocket log streaming with structured logging
- ✅ **O-series model support** - Proper parameter handling for o1, o3, o4 models
- ✅ **Download functionality** - Clean Markdown files without page separators
- ✅ **Error resilience** - Partial result recovery and graceful degradation

## Architecture

The application is built with:

- **Backend**: Python 3.13+ with FastAPI framework and modern async patterns
- **Frontend**: Responsive web UI with real-time log viewer and download functionality
- **AI Integration**: AsyncOpenAI SDK with TaskGroup-based concurrent processing
- **PDF Processing**: pdf2image library with configurable DPI and format
- **Package Management**: uv with structured dependencies

## Core Components

### API Endpoints
- `GET /` - Serves the main HTML page for web UI
- `GET /models` - Returns available OpenAI vision models via client.models.list()
- `POST /convert` - Accepts multipart/form-data with PDF files, model selection, and detail level

### Processing Flow
1. **Upload & Validation**: Receive PDF files via web form with multi-file support
2. **PDF Processing**: Convert each page to high-resolution images (300 DPI PNG by default)
3. **Concurrent Processing**: Use TaskGroup to process multiple pages simultaneously (1-100 concurrency)
4. **Model Detection**: Automatically handle o-series models (max_completion_tokens, no temperature)
5. **Error Recovery**: Continue processing successful pages even if some fail
6. **Result Assembly**: Combine pages with clean spacing (no horizontal rules)
7. **Download Ready**: Return clean Markdown with browser download functionality

### Key Features
- **High-concurrency processing** (1-100 simultaneous requests)
- **All OpenAI models supported** including o1, o3, o4 series
- **Real-time progress monitoring** via WebSocket log streaming
- **Partial result recovery** - get successful pages even if some fail
- **Clean Markdown output** without artificial page separators
- **One-click downloads** with automatic .pdf → .md filename conversion

## Development Commands

### Installation
```bash
uv sync --dev  # Install dependencies
playwright install  # Install browser drivers for testing
```

### Running the Application
```bash
uv run python -m src.modul8r.main  # Start development server on http://127.0.0.1:8000
```

### Testing
```bash
uv run pytest  # Run all tests
uv run pytest tests/test_services.py  # Run unit tests only
uv run pytest tests/test_main.py  # Run API tests only
uv run pytest tests/test_playwright.py  # Run web UI tests only (mocked)
```

### End-to-End Testing with Playwright
The project includes comprehensive E2E tests that use Playwright to automate browser interactions and test the complete PDF-to-Markdown conversion workflow. These tests are configured via YAML profiles and run against the real application with actual OpenAI API calls.

#### E2E Test Configuration
E2E tests are configured via `playwright-e2e/profiles.yaml`. Each profile defines:
- PDF file to test (must exist in `playwright-e2e/` directory)
- OpenAI model to use (any available model - no hardcoded restrictions)
- Processing parameters (detail level, concurrency)
- Timeout settings and browser configuration

#### Default E2E Profiles
- **quick_e2e**: Fast test using `gpt-4.1-nano` model with low detail and 32 concurrency
- **long_e2e**: Comprehensive test using `o3` model with high detail and 64 concurrency
- **gpt4_turbo_test**: Example profile for testing GPT-4 Turbo
- **stress_test**: High concurrency test with 100 concurrent requests

#### Running E2E Tests
```bash
# List available E2E profiles
python -c "from tests.e2e_config import E2EConfig; print(list(E2EConfig().get_profiles().keys()))"

# Run specific E2E profile
uv run pytest tests/test_e2e_playwright.py::TestE2EProfiles::test_e2e_profile_browser_automation[quick_e2e]
uv run pytest tests/test_e2e_playwright.py::TestE2EProfiles::test_e2e_profile_browser_automation[long_e2e]

# Run all E2E profile tests
uv run pytest tests/test_e2e_playwright.py::TestE2EProfiles -m e2e

# Run E2E infrastructure tests
uv run pytest tests/test_e2e_playwright.py::TestE2EInfrastructure

# Run all E2E tests (infrastructure + profiles)
uv run pytest tests/test_e2e_playwright.py -m slow

# Run with visible browser for debugging
PLAYWRIGHT_HEADLESS=false uv run pytest tests/test_e2e_playwright.py::TestE2EProfiles::test_e2e_profile_browser_automation[quick_e2e] -s
```

#### Adding New E2E Profiles
SDETs can add new test profiles by editing `playwright-e2e/profiles.yaml`:

```yaml
custom_profile:
  name: "Custom Test Profile"
  description: "Testing specific scenario"
  pdf_file: "custom.pdf"  # Must exist in playwright-e2e/
  model: "gpt-4o-mini"    # Any OpenAI model
  detail_level: "high"    # "low" or "high"
  concurrency: 8          # 1-100
  timeout_minutes: 12     # Max wait time

  # Optional browser overrides
  browser_overrides:
    headless: true        # Override global browser settings
    slow_mo: 0           # Run at full speed
```

#### Validating E2E Configuration
```bash
# Validate all profiles
python -m tests.e2e_config --validate

# Check specific profile
python -m tests.e2e_config --profile quick_e2e

# Test profile configuration without running full test
python -m tests.e2e_config --profile custom_profile --dry-run
```

#### E2E Test Requirements
- `OPENAI_API_KEY` environment variable must be set
- PDF files must exist in `playwright-e2e/` directory
- System dependencies: poppler-utils (for PDF processing)
- Browser dependencies: `playwright install` must be run

#### E2E Test Features
The E2E tests use Playwright to automate:
- **Browser launch and navigation** to the web application
- **Dynamic model loading** via real OpenAI API calls
- **Form interactions** (file uploads, dropdowns, sliders, checkboxes)
- **WebSocket log monitoring** in real-time during processing
- **Conversion progress tracking** through UI state changes
- **Result verification** and content validation
- **Download functionality** testing with actual file generation
- **Error handling** and timeout scenarios

These tests surface issues in the core library that might be triggered by specific models or configurations, ensuring robust operation across all supported OpenAI models.

### Code Quality
```bash
uv run ruff check  # Lint code
uv run ruff format  # Format code
uv run mypy src/  # Type checking
```

### Pytest Markers
The project uses specific pytest markers for test organization:
- `slow`: Tests that may take several minutes (e.g., E2E with real API calls)
- `integration`: Integration tests
- `unit`: Unit tests
- `phase1`: Phase 1 foundation safeguards
- `e2e`: End-to-end browser automation tests

Run specific test categories with: `uv run pytest -m unit` or `uv run pytest -m "not slow"`

### Environment Setup
The application requires an OpenAI API key. Create a `.env` file in the project root with:
```bash
OPENAI_API_KEY="your-api-key-here"
```

Alternatively, set the `OPENAI_API_KEY` environment variable or pass it to the OpenAIService constructor.

### System Dependencies
- poppler-utils (for pdf2image library)
  - macOS: `brew install poppler`
  - Ubuntu/Debian: `apt-get install poppler-utils`
  - Windows: Download from poppler website

## Logging System

The application uses structured logging with the following features:

### Configuration
- **JSON Format**: Structured logs with consistent fields (timestamp, level, request_id, etc.)
- **Request Correlation**: All logs within a request share the same request_id for tracing
- **WebSocket Streaming**: Real-time log streaming to web clients (configurable)
- **Deduplication**: Prevents duplicate log entries

### Settings
```bash
MODUL8R_LOG_LEVEL=INFO           # DEBUG, INFO, WARNING, ERROR
MODUL8R_LOG_FORMAT=json          # json or console
MODUL8R_ENABLE_LOG_CAPTURE=true  # Enable WebSocket log streaming
```

### Log Levels
- **DEBUG**: Detailed processing information
- **INFO**: Standard operation events (requests, processing status)
- **WARNING**: Non-critical issues (API fallbacks, file skips)
- **ERROR**: Processing failures and exceptions

### WebSocket Log Streaming
- Endpoint: `ws://localhost:8000/ws/logs`
- Only active when clients are connected (performance optimized)
- JSON messages: `{"type": "log_entry", "log": {...}}`

## Recent Updates

### Version 0.1.0 - Production Release
- **Async Architecture**: Implemented Python 3.13 TaskGroup for concurrent processing
- **Model Compatibility**: Added support for o-series models (o1, o3, o4) with proper parameters
- **Enhanced UI**: Added download buttons and real-time log viewer
- **Error Resilience**: Improved partial result recovery and graceful failure handling
- **Performance**: Configurable concurrency from 1-100 concurrent requests
- **Clean Output**: Removed page separators for seamless Markdown documents

### Critical Fixes Applied
- **Duplicate Logging**: Resolved WebSocket log duplication with proper deduplication
- **Retry Loops**: Limited retry attempts to prevent endless processing cycles
- **TaskGroup Errors**: Improved exception handling for concurrent operations
- **Memory Management**: Added cleanup for log entries and task results

## Development Notes

This project prioritizes fidelity and accuracy in converting scanned tabletop RPG documents to clean, structured Markdown format. The modern async architecture ensures high performance while maintaining reliability through comprehensive error handling and partial result recovery.

### Markdown Style Guidelines
All Markdown output follows the project's style guide (`docs/mdstyle.md`):

- Headings use sentence case and are surrounded by blank lines
- Unordered lists use hyphens for list markers
- Code blocks are surrounded by blank lines
- No horizontal rule separators (---) are used