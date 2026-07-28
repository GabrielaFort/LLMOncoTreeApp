# LLM OncoTree App

Streamlit app for running the [LLM OncoTree classifier](https://github.com/HuntsmanCancerInstitute/OncoTree/tree/master).

The app accepts pathology reports (`.pdf`, `.txt`, `.docx`), OncoTree input JSON, Tempus v3.3+ JSON, and manual form entry. Report-style inputs are parsed with utilities from [`LLMPathReportParser`](https://github.com/GabrielaFort/LLMPathReportParser) before classification.

This repository contains the Streamlit app and classifier runner. Additional runtime dependencies are fetched during setup.

A freely available version of the app is hosted at http://tanlab.utah.edu:8094/. This version is limited to Ollama cloud model use and requires an API key from Ollama to access cloud models. This version also has a batch submission limit of 10 files at a time. 

**Warning**: Do not upload any PHI/PII to cloud-hosted AI models. To run the application using local models, read the instructions below.

## Repository Layout

```text
app.py                         Streamlit frontend
oncotree_runner.py             Python wrapper around the Java OncoTree classifier
batch_classify.py              Batch command-line classifier runner
evaluate_tcga_benchmark.py     Benchmark evaluation script
full_oncotree.json             OncoTree display data used by the app
scripts/setup_external_deps.py Fetches external runtime dependencies
docker/                        Dockerfile and Compose config
```

After setup, external dependencies are stored outside git:

```text
.external/
  LLMPathReportParser/    Cloned from GabrielaFort/LLMPathReportParser
  runtime/
    OT.jar                Downloaded from latest OncoTree release
    USeq/                 Downloaded from latest USeq release
      Apps/TempusPathoPrinter
      LibraryJars/
    OTResources/          Extracted from OncoTree/Resources/OTResources13July2026.zip
```

## Requirements

- Python 3.10+
- Java 21+
- Ollama installed and running for local models
- Optional Ollama Cloud API key for cloud models

## Install

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

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Fetch external runtime dependencies:

```bash
python scripts/setup_external_deps.py
```

## Run The App

```bash
streamlit run app.py
```

The app supports:

- uploaded `.pdf`, `.txt`, `.docx`, and `.json` files
- manual form entry
- batch uploaded file classification
- local Ollama models
- Ollama Cloud models

## Run With Docker

The Docker setup builds a self-contained image with the Streamlit app, Java 21 runtime, Python dependencies, `LLMPathReportParser`, OncoTree resources, the OncoTree classifier JAR, and USeq runtime files. Docker runs `scripts/setup_external_deps.py` during image build, so you do not need to run the setup script first.

From `LLMOncoTreeApp`, build and run the app locally with Compose (this may take several minutes):

```bash
docker compose -f docker/docker-compose.yml up --build
```

Then open:

```text
http://localhost:8501
```

To stop the app:

```bash
docker compose -f docker/docker-compose.yml down
```


### Docker And Ollama

The container does not run Ollama itself. For local models, keep Ollama running on the host machine. Docker defaults to the host Ollama address:

```text
OLLAMA_HOST=http://host.docker.internal:11434
```

This is already set in `docker/docker-compose.yml` and the `Dockerfile`. You only need to change `OLLAMA_HOST` if Ollama is running on a different host or port.

For Ollama on the same Linux host with a custom port:

```yaml
services:
  oncotree-app:
    environment:
      OLLAMA_HOST: http://host.docker.internal:28641
      RUN_ENVIRONMENT: LOCAL
    extra_hosts:
      - "host.docker.internal:host-gateway"
```

For Ollama on another reachable machine, use that machine's IP address or hostname:

```yaml
services:
  oncotree-app:
    environment:
      OLLAMA_HOST: http://192.168.1.25:11434
      RUN_ENVIRONMENT: LOCAL
```

Use one of these patterns:

- **Mac or Windows Docker Desktop, Ollama on the same computer:** use `http://host.docker.internal:11434`.
- **Linux Docker, Ollama on the same computer:** use `http://host.docker.internal:<port>` and keep the `extra_hosts` entry.
- **Ollama on another server:** use that server's IP address or hostname, such as `http://192.168.1.25:11434`, and remove `extra_hosts`.


Ollama Cloud models do not require a local Ollama server, but the app still requires an Ollama Cloud API key before cloud model classification.


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

- `.pdf` files are displayed in the app, converted to text using [Docling](https://www.docling.ai/), then parsed into OncoTree input JSON.
- `.txt` files are parsed into OncoTree input JSON.
- `.docx` files are converted to text, then parsed into OncoTree input JSON.

The selected LLM is used for this report-parsing step. After parsing, the Java OncoTree classifier runs on the generated JSON.

### JSON Uploads

`.json` uploads skip report parsing. They must be one of:

- **OncoTree input JSON**, with the fields described below.
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


