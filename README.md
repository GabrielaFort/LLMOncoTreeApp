# LLM OncoTree App

Streamlit app for running the [LLM OncoTree classifier](https://github.com/HuntsmanCancerInstitute/OncoTree/tree/master).

**Warning: Do not upload any PHI/PII to cloud-hosted AI models or unapproved systems. To run the application using local models, read the instructions below.**

The app accepts pathology reports (`.pdf`, `.txt`, `.docx`), OncoTree input JSON, Tempus v3.3+ JSON, and manual form entry. Report-style inputs are parsed with utilities from [LLMPathReportParser](https://github.com/GabrielaFort/LLMPathReportParser) before classification.

A freely available version of the app is hosted at http://tanlab.utah.edu:8094/. This version is limited to Ollama cloud model use and requires an API key from Ollama to access cloud models. This version also has a batch submission limit of 10 files at a time. 

## Repository Layout

```text
app.py                         Streamlit frontend
oncotree_runner.py             Python wrapper around the Java OncoTree classifier
batch_classify.py              Batch command-line classifier runner
full_oncotree.json             OncoTree display data used by the app
scripts/setup_external_deps.py Fetches external runtime dependencies
docker/                        Dockerfile and Compose config
local_test/USeq/               Tracked USeq runtime files used during setup
```

External dependencies downloaded during setup:

```text
.external/
  LLMPathReportParser/    Cloned from GabrielaFort/LLMPathReportParser
  runtime/
    OT.jar                Downloaded from latest OncoTree release
    USeq/                 Copied from tracked local_test/USeq runtime files
      Apps/TempusPathoPrinter
      LibraryJars/
    OTResources/          Extracted from OncoTree/Resources/OTResources13July2026.zip
```

## Requirements

- Docker for the recommended installation.
- Ollama installed and running on the host machine for local models.
- Optional Ollama Cloud API key for cloud models.

For manual source installs, use Python 3.10+ and Java 21+.

## Run With Docker

The easiest way to run the app locally is to pull the prebuilt container image from GitHub Container Registry. The image includes the Streamlit app, Java 21 runtime, Python dependencies, [LLMPathReportParser](https://github.com/GabrielaFort/LLMPathReportParser), OncoTree resources, the [OncoTree classifier app](https://github.com/HuntsmanCancerInstitute/OncoTree/tree/master), and the TempusPathoPrinter ([USeq Repo](https://github.com/HuntsmanCancerInstitute/USeq)) for parsing Tempus JSON reports.

Install Docker, then run:

```bash
docker run --rm \
  -p 8501:8501 \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  --add-host=host.docker.internal:host-gateway \
  ghcr.io/gabrielafort/llm-oncotree-app:latest
```

Then open:

```text
http://localhost:8501
```

To stop the app, press `Ctrl+C` in the terminal running Docker.

### Docker And Ollama

The container does not run Ollama itself. For local models, keep Ollama running on the host machine. The Docker command above sets the host Ollama address:

```text
OLLAMA_HOST=http://host.docker.internal:11434
```

You only need to change `OLLAMA_HOST` if Ollama is running on a different host or port.

For Ollama on the same Linux host with a custom port:

```bash
docker run --rm \
  -p 8501:8501 \
  -e OLLAMA_HOST=http://host.docker.internal:28641 \
  -e RUN_ENVIRONMENT=LOCAL \
  --add-host=host.docker.internal:host-gateway \
  ghcr.io/gabrielafort/llm-oncotree-app:latest
```

For Ollama on another reachable machine, use that machine's IP address or hostname:

```bash
docker run --rm \
  -p 8501:8501 \
  -e OLLAMA_HOST=http://192.168.1.25:11434 \
  -e RUN_ENVIRONMENT=LOCAL \
  ghcr.io/gabrielafort/llm-oncotree-app:latest
```

Use one of these patterns:

- **Mac or Windows Docker Desktop, Ollama on the same computer:** use `http://host.docker.internal:11434`.
- **Linux Docker, Ollama on the same computer:** use `http://host.docker.internal:<port>` and keep `--add-host=host.docker.internal:host-gateway`.
- **Ollama on another server:** use that server's IP address or hostname, such as `http://192.168.1.25:11434`.

Ollama Cloud models do not require a local Ollama server, but the app still requires an Ollama Cloud API key before cloud model classification.

<details>
<summary>Manual install options</summary>

### Build The Docker Image Yourself

Use this option if you want to build the container from source instead of pulling the prebuilt GitHub image.

Clone this repository:

```bash
git clone https://github.com/GabrielaFort/LLMOncoTreeApp.git
cd LLMOncoTreeApp
```

Build the image:

```bash
docker build \
  -f docker/Dockerfile \
  -t llm-oncotree-app:local \
  .
```

Run the locally built image:

```bash
docker run --rm \
  -p 8501:8501 \
  -e OLLAMA_HOST=http://host.docker.internal:11434 \
  --add-host=host.docker.internal:host-gateway \
  llm-oncotree-app:local
```

Local builds may take several minutes because Docker installs Python dependencies and runs `scripts/setup_external_deps.py` during the image build.

You can also build and run with Docker Compose:

```bash
docker compose -f docker/docker-compose.yml up --build
```

To stop the Compose app:

```bash
docker compose -f docker/docker-compose.yml down
```

### Install And Run From Source

Use this option if you do not want to use Docker.

Clone this repository:

```bash
git clone https://github.com/GabrielaFort/LLMOncoTreeApp.git
cd LLMOncoTreeApp
```

Create and activate a Python environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Fetch external runtime dependencies:

```bash
python scripts/setup_external_deps.py
```

Run the app:

```bash
python -m streamlit run app.py
```

Use `python -m streamlit` so the app runs with the same Python environment where you installed `requirements.txt`.

</details>


## Accepted Inputs And Behavior

The Streamlit app has three input modes:

- **File Upload** for one document or JSON case at a time.
- **Form Upload** for manually entering one case without uploading a file.
- **Batch Upload** for processing multiple uploaded files in one run.

### File Upload

File Upload accepts exactly one file with one of these extensions:

- `.pdf`
- `.txt`
- `.docx`
- `.json`

Pathology Report-style files are parsed before classification:

- `.pdf` files are displayed in the app, converted to text using [Docling](https://www.docling.ai/), then parsed into OncoTree input JSON using the selected LLM. The app defaults to processing the first 5 PDF pages; users can change the page limit before classification.
- `.txt` files are parsed into OncoTree input JSON.
- `.docx` files are converted to text, then parsed into OncoTree input JSON.

The selected LLM is used for this report-parsing step. After parsing, the Java OncoTree classifier runs on the generated JSON.

If uploading long PDFs where the majority of the diagnosis information is in the first few pages, setting a page limit can significantly reduce processing time without compromising accuracy.

### JSON Uploads

`.json` uploads skip report parsing. They must be one of:

- **OncoTree input JSON**, with the fields described in the [OncoTree Repo](https://github.com/HuntsmanCancerInstitute/OncoTree).
- **Tempus v3.3+ JSON**, detected by fields such as `metadata`, `rna`, or `ihc`. These reports are automatically parsed into OncoTree input JSONs using the TempusPathoPrinter ([USeq Repo](https://github.com/HuntsmanCancerInstitute/USeq))

For a single JSON upload, the app lets users choose the JSON type or use auto-detection. Batch uploads auto-detect each JSON file by default, with an option to force all JSON files to one type.

### Form Upload

Form Upload creates one OncoTree input JSON record from manual entries:

- `Case ID / test order ID`: optional; a random case ID is generated if left blank.
- `Sample site`: where the tumor sample was collected.
- `Sample Type`: optional primary/metastasis, grade, stage, or related sample details.
- `Diagnosis`: short diagnostic description.
- `Other Classification Information`: optional ICD code description text.
- `Comments`: optional longer pathology comments, including IHC or other supporting details.

At least one of `Diagnosis`, `Other Classification Information`, or `Comments` is required.

### Batch Upload

Batch Upload accepts multiple files with these extensions:

- `.pdf`
- `.txt`
- `.docx`
- `.json`

When a batch includes PDFs, the app shows a PDF page limit control. It defaults to 5 pages and applies to each PDF in the batch.
