# modul8r

Web service that converts PDF files to Markdown using OpenAI vision models.

modul8r converts PDF pages to images and sends them to OpenAI's vision models for text extraction and Markdown conversion. Uses FastAPI backend with WebSocket log streaming.

![modul8r web interface](modul8r-screenshot.png)

## Features

- PDF to image conversion using pdf2image
- OpenAI vision model integration with automatic o-series parameter handling
- Concurrent page processing using Python 3.13 TaskGroup (1-100 concurrent requests)
- WebSocket log streaming for real-time processing visibility
- Partial result recovery when some pages fail processing
- Configurable concurrency and processing parameters

## Prerequisites

- Python 3.13 or higher
- OpenAI API key
- System dependencies:
  - **macOS**: `brew install poppler`
  - **Ubuntu/Debian**: `apt-get install poppler-utils`
  - **Windows**: Download poppler from the official website

## Installation

```bash
# Clone the repository
git clone https://github.com/your-username/modul8r.git
cd modul8r

# Install dependencies
uv sync --dev

# Install browser drivers for testing (optional)
playwright install
```

## Configuration

Set your OpenAI API key:

```bash
export OPENAI_API_KEY="your-api-key-here"
```

Or create a `.env` file:

```
OPENAI_API_KEY=your-api-key-here
```

## Running the application

```bash
uv run python -m src.modul8r.main
```

The web interface will be available at http://127.0.0.1:8000

## Usage

### Web interface

1. Open your browser to http://127.0.0.1:8000
2. Upload PDF file(s)
3. Select OpenAI model (defaults to first available model)
4. Set detail level (low/high - defaults to high)
5. Set concurrency (1-100 - defaults to 3)
6. Click "Convert"
7. View processing logs via WebSocket connection
8. Receive JSON response with converted Markdown

### API endpoints

#### GET /models

Returns available OpenAI vision models:

```bash
curl http://localhost:8000/models
```

#### POST /convert

Convert PDF files to Markdown (accepts multipart form data):

```bash
curl -X POST \
  -F "files=@document.pdf" \
  -F "model=gpt-4o" \
  -F "detail=high" \
  -F "concurrency=5" \
  http://localhost:8000/convert
```

Returns JSON: `{"filename.pdf": "converted markdown content"}`

#### GET /config

Returns current configuration settings.

#### GET /status

Application health check and status.

#### WebSocket /ws/logs

Real-time log streaming:

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/logs');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  // Message types: log_entry, log_history, status_update, pong
};
```

## Configuration

Configuration via environment variables (most use `MODUL8R_` prefix):

### OpenAI settings

- `OPENAI_API_KEY` - Your OpenAI API key (uses alias, no prefix)
- `MODUL8R_OPENAI_DEFAULT_MODEL` - Default model (default: "gpt-4o")
- `MODUL8R_OPENAI_MAX_TOKENS` - Max tokens per request (default: 4096)
- `MODUL8R_OPENAI_TEMPERATURE` - Temperature setting (default: 0.1)
- `MODUL8R_OPENAI_TIMEOUT` - Request timeout in seconds (default: 60.0)

### Processing settings

- `MODUL8R_MAX_CONCURRENT_REQUESTS` - Concurrent processing limit (default: 3, range: 1-100)
- `MODUL8R_PDF_PROCESSING_TIMEOUT` - Overall processing timeout (default: 300.0)
- `MODUL8R_PDF_DPI` - Image resolution for PDF conversion (default: 300, range: 150-600)
- `MODUL8R_PDF_FORMAT` - Image format (default: "PNG")
- `MODUL8R_RETRY_MAX_ATTEMPTS` - Max retry attempts (default: 1)
- `MODUL8R_RETRY_BASE_DELAY` - Base retry delay in seconds (default: 1.0)
- `MODUL8R_RETRY_MAX_DELAY` - Max retry delay in seconds (default: 60.0)

### Logging settings

- `MODUL8R_LOG_LEVEL` - Logging level (default: "INFO")
- `MODUL8R_LOG_FORMAT` - Log format (default: "json")
- `MODUL8R_LOG_CORRELATION_ID_HEADER` - Correlation ID header (default: "X-Correlation-ID")
- `MODUL8R_ENABLE_LOG_CAPTURE` - Enable WebSocket log streaming (default: true)

### Server settings

- `MODUL8R_SERVER_HOST` - Server host (default: "127.0.0.1")
- `MODUL8R_SERVER_PORT` - Server port (default: 8000)
- `MODUL8R_SERVER_RELOAD` - Enable auto-reload (default: false)

## Development

### Running tests

```bash
# Run all tests
uv run pytest

# Run specific test suites
uv run pytest tests/test_services.py    # Unit tests
uv run pytest tests/test_main.py        # API tests
uv run pytest tests/test_playwright.py  # Web UI tests

# Validate logging configuration
uv run python test_logging_fix.py
```

### Code quality

```bash
# Lint code
uv run ruff check

# Format code
uv run ruff format

# Type checking
uv run mypy src/
```

### Project structure

```
modul8r/
├── src/modul8r/           # Main application code
│   ├── main.py           # FastAPI application and routes
│   ├── services.py       # OpenAI and PDF processing services
│   ├── config.py         # Configuration management
│   ├── logging_config.py # Structured logging setup
│   └── websocket_handlers.py # WebSocket connection management
├── templates/            # Jinja2 HTML templates
├── tests/               # Test suites
├── docs/                # Project documentation
├── pyproject.toml       # Project dependencies and configuration
└── CLAUDE.md           # Development guidance
```

## Architecture

### Components

- FastAPI web framework
- AsyncOpenAI client with model detection and parameter handling
- pdf2image for PDF to PNG conversion at configurable DPI
- Python 3.13 TaskGroup for concurrent page processing
- WebSocket server for log streaming
- Structured logging with request correlation

### Processing flow

1. Accept PDF files via multipart form upload
2. Convert PDF pages to images using pdf2image
3. Base64 encode images for OpenAI API
4. Process pages concurrently using TaskGroup and semaphore rate limiting
5. Send images to OpenAI vision model with structured prompt
6. Collect successful page results, skip failed pages
7. Return JSON response mapping filenames to Markdown content

### WebSocket logging

- Streams structured logs to connected clients
- Message types: log_entry, log_history, status_update, pong
- Includes request correlation IDs and deduplication
- Configurable via MODUL8R_ENABLE_LOG_CAPTURE

## Troubleshooting

### Common issues

**Import errors or missing dependencies:**

```bash
uv sync --dev
```

**PDF conversion fails:**
- Ensure poppler-utils is installed
- Check PDF file permissions and format

**OpenAI API errors:**
- Verify your API key is set correctly
- Check your OpenAI account usage and limits
- Some models may not be available in your region

**WebSocket connection issues:**
- Check firewall settings for localhost connections
- Ensure browser supports WebSockets

**Memory issues with large PDFs:**
- Reduce concurrency setting
- Process files individually rather than in batches
- Consider using lower DPI settings

### Performance tuning

- Adjust `MODUL8R_MAX_CONCURRENT_REQUESTS` (default: 3, max: 100)
- Lower `MODUL8R_PDF_DPI` for faster processing (default: 300, min: 150)
- Use "low" detail level for OpenAI vision processing
- Note: retry_max_attempts is set to 1 to prevent retry loops
