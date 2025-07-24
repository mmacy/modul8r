# Playwright end-to-end (E2E) test profiles

Settings to use for Playwright E2E tests intended to test real-world application functionality without mocks. The tests
should launch the application, specify the settings for one of the following profiles, then run the PDF-to-Markdown
conversion. These tests are to be run in an ad-hoc fashion rather than on every unit or integration test pass, typically
initiated or requested by the user.

## Quick E2E

- Model: gpt-4.1-nano
- PDF: playwright-e2e/quick.pdf
- Image detail level: Low
- Concurrent requests: 32

## Long E2E

- Model: o3
- PDF: playwright-e2e/long.pdf
- Image detail level: High
- Concurrent requests: 64
