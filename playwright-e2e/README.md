# Playwright end-to-end testing for modul8r

This directory contains the configuration and test files for comprehensive end-to-end testing of the modul8r PDF-to-Markdown conversion application using Playwright browser automation.

## Overview

The E2E testing system uses **Playwright** to automate real browser interactions, testing the complete workflow from PDF upload through Markdown conversion and download. Tests are configured via YAML profiles, allowing SDETs to add, modify, and remove test scenarios without touching source code.

### What these tests do

1. **Launch a real browser** (Chromium by default)
2. **Start the modul8r application** with actual OpenAI API integration
3. **Navigate to the web interface** and interact with forms
4. **Upload PDF files** and configure processing parameters
5. **Monitor real-time logs** via WebSocket connections
6. **Wait for conversion completion** and validate results
7. **Test download functionality** with actual file generation
8. **Verify error handling** and timeout scenarios

## Quick start

### Prerequisites

```bash
# 1. Install dependencies
uv sync --dev

# 2. Install Playwright browsers
uv run playwright install

# 3. Set OpenAI API key (required for real tests)
export OPENAI_API_KEY="your-api-key-here"
```

### Run your first E2E test

```bash
# List available test profiles
python -c "from tests.e2e_config import E2EConfig; print(list(E2EConfig().get_profiles().keys()))"

# Run the quick profile (recommended for first test)
uv run pytest tests/test_e2e_playwright.py::TestE2EProfiles::test_e2e_profile_browser_automation[quick_e2e] -s

# Run with visible browser (great for debugging)
PLAYWRIGHT_HEADLESS=false uv run pytest tests/test_e2e_playwright.py::TestE2EProfiles::test_e2e_profile_browser_automation[quick_e2e] -s
```

## Test profiles

Test profiles are defined in `profiles.yaml`.

| Profile             | Model        | PDF File  | Detail | Concurrency | Timeout | Purpose                |
| ------------------- | ------------ | --------- | ------ | ----------- | ------- | ---------------------- |
| **quick_e2e**       | gpt-4.1-nano | quick.pdf | low    | 32          | 5 min   | Fast smoke test        |
| **long_e2e**        | o3           | long.pdf  | high   | 64          | 15 min  | Comprehensive test     |
| **stress_test**     | gpt-4.1-nano | long.pdf  | low    | 100         | 10 min  | High concurrency test  |

## Directory structure

```console
playwright-e2e/
├── README.md              # This file - SDET guide
├── profiles.yaml          # Test profile configurations
├── profile-schema.yaml    # YAML validation schema
├── playwright-e2e.md      # Original requirements document
├── quick.pdf              # Small PDF for fast tests
└── long.pdf               # Larger PDF for comprehensive tests
```

## Adding new test profiles

### Step 1: Add your PDF file

Place your test PDF in this directory:
```bash
cp /path/to/your/test.pdf playwright-e2e/custom-test.pdf
```

### Step 2: Add profile configuration

Edit `profiles.yaml` and add your profile:

```yaml
my_custom_test:
  name: "My Custom E2E Test"
  description: "Testing specific edge case scenario"
  pdf_file: "custom-test.pdf"        # Must exist in this directory
  model: "gpt-4.1-nano"               # Any OpenAI model
  detail_level: "low"               # "low" or "high"
  concurrency: 8                     # 1-100 concurrent requests
  timeout_minutes: 12                # Max wait time for completion

  # Optional: Override browser settings for this profile
  browser_overrides:
    headless: true                   # Run without visible browser
    slow_mo: 0                      # Full speed (no slow motion)
```

### Step 3: Validate configuration

```bash
# Validate all profiles
python -m tests.e2e_config --validate

# Test your specific profile
python -m tests.e2e_config --profile my_custom_test --dry-run
```

### Step 4: Run your test

```bash
uv run pytest tests/test_e2e_playwright.py::TestE2EProfiles::test_e2e_profile_browser_automation[my_custom_test] -s
```

## Common commands

### Configuration management
```bash
# List all available profiles
python -m tests.e2e_config --list

# Show details for specific profile
python -m tests.e2e_config --profile quick_e2e

# Validate all profile configurations
python -m tests.e2e_config --validate

# Test profile without running full browser test
python -m tests.e2e_config --profile long_e2e --dry-run
```

### Running tests
```bash
# Run specific profile
uv run pytest tests/test_e2e_playwright.py::TestE2EProfiles::test_e2e_profile_browser_automation[quick_e2e]

# Run all E2E profile tests
uv run pytest tests/test_e2e_playwright.py::TestE2EProfiles -m e2e

# Run infrastructure tests (WebSocket, status endpoints)
uv run pytest tests/test_e2e_playwright.py::TestE2EInfrastructure

# Run all E2E tests (infrastructure + profiles)
uv run pytest tests/test_e2e_playwright.py -m slow

# Run with visible browser for debugging
PLAYWRIGHT_HEADLESS=false uv run pytest tests/test_e2e_playwright.py::TestE2EProfiles::test_e2e_profile_browser_automation[stress_test] -s -v
```

### Filtering and selection
```bash
# Run only E2E marked tests
uv run pytest tests/test_e2e_playwright.py -m e2e

# Run only slow tests
uv run pytest tests/test_e2e_playwright.py -m slow

# Run specific test types
uv run pytest tests/test_e2e_playwright.py::TestE2EProfiles::test_e2e_profile_concurrent_processing -m e2e

# Run tests matching pattern
uv run pytest tests/test_e2e_playwright.py -k "quick_e2e"
```

## Browser configuration

Global browser settings are in `profiles.yaml` under `browser_settings`:

```yaml
browser_settings:
  headless: false          # Show browser during test execution
  slow_mo: 500            # Slow down actions (milliseconds)
  viewport:
    width: 1280
    height: 720
  timeout: 60000          # Default timeout for Playwright actions
  screenshot_on_failure: true
  video_recording: false  # Set to true to record test execution
```

You can override these per-profile using `browser_overrides` in individual profiles.

## Test types available

### 1. Browser automation tests (`test_e2e_profile_browser_automation`)

- **Full workflow testing**: Upload → Configure → Process → Download
- **Real API integration**: Uses actual OpenAI models
- **WebSocket monitoring**: Watches real-time logs during processing
- **UI validation**: Verifies all form interactions and state changes

### 2. Concurrent processing tests (`test_e2e_profile_concurrent_processing`)

- **High concurrency validation**: Tests system under load
- **Performance monitoring**: Tracks processing with multiple concurrent requests
- **Resource management**: Validates system behavior at scale

### 3. Download functionality tests (`test_e2e_profile_download_functionality`)

- **File generation**: Tests actual Markdown file creation
- **Browser download handling**: Validates download triggers and file properties
- **Content verification**: Ensures downloaded files contain expected content

## Debugging guide

### Common issues

**Test fails with "Model not available":**
```bash
# Check what models are actually available
uv run python -c "
from tests.e2e_config import E2EConfig
config = E2EConfig()
profile = config.get_profile('your_profile')
print('Requested model:', profile['model'])
"

# Then run a real server and check /models endpoint
curl http://localhost:8000/models
```

**PDF file not found:**
```bash
# Verify your PDF exists
ls -la playwright-e2e/your-file.pdf

# Check profile configuration
python -m tests.e2e_config --profile your_profile
```

**Browser doesn't start:**
```bash
# Reinstall Playwright browsers
uv run playwright install

# Test browser installation
uv run python -c "
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    page = browser.new_page()
    page.goto('https://example.com')
    print('Browser test successful!')
    browser.close()
"
```

### Debug mode

For visual debugging, always use:
```bash
PLAYWRIGHT_HEADLESS=false uv run pytest <your-test> -s -v --tb=short
```

This will:

- Show the browser window
- Print detailed output (`-s`)
- Show verbose test info (`-v`)
- Use shorter tracebacks (`--tb=short`)

### Log analysis

The tests integrate with modul8r's real-time logging system. During test execution, you'll see:

- **Server startup logs**: FastAPI server initialization
- **WebSocket connection logs**: Real-time log streaming setup
- **Processing logs**: PDF conversion progress
- **API interaction logs**: OpenAI model requests and responses

## Performance expectations

| Profile             | Expected Duration | Resource Usage     | When to Use              |
| ------------------- | ----------------- | ------------------ | ------------------------ |
| **quick_e2e**       | 2-5 minutes       | Low (gpt-4.1-nano) | Smoke tests, CI/CD       |
| **long_e2e**        | 5-15 minutes      | High (o3 model)    | Comprehensive validation |
| **gpt4_turbo_test** | 3-8 minutes       | Medium             | Model-specific testing   |
| **stress_test**     | 5-10 minutes      | High concurrency   | Load testing             |

## Best practices

### For regular testing

1. Start with `quick_e2e` for smoke tests
2. Use `PLAYWRIGHT_HEADLESS=false` when developing new profiles
3. Validate configurations with `--dry-run` before full tests
4. Keep PDF files small for faster iteration

### For CI/CD integration

1. Use `headless: true` in browser settings
2. Set appropriate timeouts based on expected model performance
3. Run infrastructure tests separately from profile tests
4. Consider parallel execution for multiple profiles

### For model testing

1. Create profile-specific configurations for each model
2. Use consistent PDF files across model comparisons
3. Document expected behavior differences between models
4. Test both low and high detail levels

## Troubleshooting

### Environment issues
```bash
# Verify Python environment
uv run python --version  # Should be 3.13+

# Check installed packages
uv pip list | grep -E "(playwright|pytest|pyyaml)"

# Verify API key
echo $OPENAI_API_KEY | cut -c1-10  # Should show first 10 chars
```

### Configuration issues
```bash
# Validate YAML syntax
python -c "import yaml; yaml.safe_load(open('playwright-e2e/profiles.yaml'))"

# Check schema validation
python -m tests.e2e_config --validate
```

### Test execution issues
```bash
# Run with maximum verbosity
uv run pytest tests/test_e2e_playwright.py::TestE2EProfiles::test_e2e_profile_browser_automation[quick_e2e] -vvv -s --tb=long

# Check server logs during test
# (In another terminal during test execution)
curl http://localhost:8002/status  # Note: port 8002 for E2E tests
```

## Getting help

1. **Configuration validation**: Use `python -m tests.e2e_config --validate`
2. **Profile testing**: Use `--dry-run` flag to test configurations
3. **Visual debugging**: Always use `PLAYWRIGHT_HEADLESS=false` when troubleshooting
4. **Log analysis**: Check WebSocket logs in the browser during test execution
5. **Model availability**: Verify models at `/models` endpoint before running tests

## Contributing new profiles

When adding profiles for team use:

1. **Use descriptive names**: `edge_case_large_pdf` not `test1`
2. **Document the purpose**: Clear description of what scenario you're testing
3. **Choose appropriate timeouts**: Based on PDF size and model complexity
4. **Test before committing**: Always validate with `--dry-run` and actual execution
5. **Consider resource usage**: High concurrency and o-series models are expensive

Remember: These tests use **real OpenAI API calls** and will consume API credits. Plan your testing accordingly!