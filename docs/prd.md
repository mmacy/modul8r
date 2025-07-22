### **Product requirements document: modul8r**

* **Version**: 1.7
* **Status**: Proposed
* **Author**: Marsh Macy
* **Date**: 2025-07-21

### **1. Introduction**

**modul8r** is a personal-use web service designed to convert scanned tabletop adventure modules (e.g., B/X, OSE, BFRPG, DCC) from PDF into a single, consolidated Markdown file. The service will use a **vision-centric approach**, leveraging an OpenAI multimodal model to analyze an image of each PDF page and generate structured text. The primary interface will be a local web application and REST API built with Python and FastAPI.

### **2. Objective**

The goal is to create a simple, efficient, and locally hosted tool that provides a high-fidelity conversion of entire PDF documents into clean, readable Markdown files. The tool will provide a web UI for ease of use and an API for programmatic access, allowing users to select the appropriate model and detail level for their needs.

### **3. Scope and features**

#### **3.1. Web UI**

* A simple web interface served directly from the FastAPI application.
* The UI will feature a form with the following components:
  * A file input that accepts one or more PDF files for batch processing.
  * A dropdown menu for model selection, populated dynamically from the /models endpoint.
  * An option to select the image detail level (low or high), defaulting to high.
  * A "Convert" button to initiate the process.
* An output area will display the generated Markdown for each processed file.

#### **3.2. API endpoints**

* **GET /**
  * Serves the main HTML page for the web UI.
* **GET /models**
  * This endpoint will query the OpenAI Models API (client.models.list()).
  * It will filter the list to return only the model IDs that support vision and are suitable for the task.
  * The response will be a JSON array of strings.
* **POST /convert**
  * The endpoint will accept a multipart/form-data request containing:
    * One or more required PDF files (application/pdf).
    * An optional model string field. If omitted, a default model will be used.
    * An optional detail string field (low or high). If omitted, high will be used.

#### **3.3. PDF processing**

* The service will receive one or more uploaded PDFs.
* For each file, it will iterate through the document and **rasterize each page** into a high-resolution image (PNG or JPEG format).
* Each resulting image will be **Base64-encoded** for transmission to the OpenAI API.

#### **3.4. Vision model interaction**

* The service will use the OpenAI Python SDK to call the client.responses.create endpoint for each page of each PDF.
* A **default model** will be used if not specified by the user.
* The request payload for each page will include:
  * A system prompt instructing the model to act as an expert at converting scanned TTRPG documents to Markdown.
  * A user message containing the Base64-encoded image and the user-selected detail level.
  * A specific instruction to return only the generated Markdown content.

#### **3.5. Response format**

* The /convert endpoint will return a JSON object where each key is an input filename and the value is the corresponding concatenated Markdown string for that file.
* Each page's content within the Markdown string will be separated by a Markdown horizontal rule (---).

### **4. Technical stack**

* **Backend language**: Python 3.13+
* **API framework**: FastAPI
* **Templating**: Jinja2
* **AI integration**: openai Python library
* **PDF rasterization**: pdf2image (with a poppler system dependency)
* **Package management**: uv

### **5. User flow**

1. The user navigates to the root URL of the locally hosted application.
2. The web page loads, populating the model selection dropdown via a call to the /models endpoint.
3. The user selects one or more PDF files, chooses a model and detail level from the form, and clicks "Convert".
4. The browser submits the form data to the /convert endpoint.
5. The application iterates through each uploaded file. For each file, it processes every page by rasterizing, encoding, and sending it to the selected OpenAI model.
6. The application concatenates the Markdown results for each file.
7. The API returns a JSON response to the front end, which then renders the resulting Markdown for each file in the output area of the web page.

### **6. Success metrics**

* **Fidelity**: The generated Markdown accurately reflects the content and structure of the source PDF documents.
* **Flexibility**: The user can successfully list and use different vision models and detail levels via the UI and API.
* **Performance**: The conversion of a typical multi-page document completes within an acceptable time frame.
* **Reliability**: The service consistently processes standard multi-page documents without errors.
* **Usability**: The web UI is intuitive and allows for the easy conversion of single or multiple documents.
* **Batch Functionality**: The service can reliably process a batch of multiple PDF files in a single request.
