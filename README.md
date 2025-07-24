# modul8r

A web application for converting tabletop RPG adventure module PDFs into Markdown using AI.

`modul8r` provides a web interface to upload one or more PDF files. It converts each page into an image and uses OpenAI's vision models to extract the text and format it as Markdown.

![modul8r web interface](modul8r-screenshot.png)

## Features

-   Convert TTRPG module PDFs to Markdown.
-   Web interface for uploading files and managing conversions.
-   Supports batch processing of multiple PDF files.
-   Adjustable settings for AI model, quality, and processing speed.
-   Download converted content as `.md` files.
-   Live log view to monitor the conversion process in real-time.

## Requirements

-   Python 3.13 or newer
-   An [OpenAI API key](https://platform.openai.com/api-keys)
-   [Poppler](https://poppler.freedesktop.org/)

## Installation

### 1. Get the code

Clone the repository to your local machine:

```shell
git clone https://github.com/mmacy/modul8r.git
cd modul8r
```

### 2. Install dependencies

Use `uv` to install the required Python packages:

```shell
uv sync
```

### 3. Set your API key

The application requires an OpenAI API key to function. Create a file named `.env` in the `modul8r` directory and add your key to it:

```shell
OPENAI_API_KEY="your-api-key-here"
```

### 4. Run the application

Start the web server from the project's root directory:

```shell
uv run python -m src.modul8r.main
```

The web interface should be available at http://127.0.0.1:8000.

## Usage

1.  Open your browser to http://127.0.0.1:8000.
2.  Select **Convert PDFs** from the sidebar navigation.
3.  Drag and drop your PDF files onto the drop zone, or click it to browse for files.
4.  (Optional) Adjust the AI model, detail level, and concurrency (processing speed). The default settings are recommended for most uses.
5.  Click the **Start conversion** button.
6.  You can monitor the progress in the results area that appears or by enabling the **Live logs** view in the **System logs** section.
7.  Once a file is converted, a **Download** button will appear next to its result.

## Troubleshooting

-   **PDF conversion fails**: Ensure you have installed the Poppler dependency for your operating system. Also, check that the PDF files are not corrupted or password-protected.
-   **OpenAI API errors**: Verify that your API key in the `.env` file is correct and that your OpenAI account has available funds or credits.
-   **Memory issues with large PDFs**: Converting very large or high-resolution PDFs can be memory-intensive. If you experience issues, try reducing the **concurrency level** on the conversion page or process files one at a time.

<details>
<summary>Advanced configuration</summary>

While the only required configuration is the `OPENAI_API_KEY`, nearly every setting can be customized using environment variables or by adding them to your `.env` file. The variable name is the setting in uppercase with a `MODUL8R_` prefix.

A few useful settings include:

-   `MODUL8R_OPENAI_DEFAULT_MODEL`: Set a different default AI model (e.g., `gpt-4o`).
-   `MODUL8R_PDF_DPI`: Change the resolution for PDF-to-image conversion (default is `300`). Higher values may improve accuracy for small text but will use more memory and take longer.
-   `MODUL8R_MAX_CONCURRENT_REQUESTS`: Change the default concurrency level for processing pages (default is `3`).

</details>
