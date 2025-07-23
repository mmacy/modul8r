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
uv run pytest tests/test_playwright.py  # Run web UI tests only
uv run python test_logging_fix.py  # Validate logging configuration
```

### Code Quality
```bash
uv run ruff check  # Lint code
uv run ruff format  # Format code
uv run mypy src/  # Type checking
```

### Environment Setup
The application requires an OpenAI API key. Set the `OPENAI_API_KEY` environment variable or pass it to the OpenAIService constructor.

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