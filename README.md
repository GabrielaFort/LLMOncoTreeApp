# LLM OncoTree App

Streamlit app for running the [LLM OncoTree classifier](https://github.com/HuntsmanCancerInstitute/OncoTree/tree/master).

The app accepts pathology reports (`.pdf`, `.txt`, `.docx`), OncoTree input JSON, Tempus v3.3+ JSON, and manual form entry. Report-style inputs are parsed with utilities from the sibling [`LLMPathReportParser`](https://github.com/GabrielaFort/LLMPathReportParser) repository before classification.

This repository contains the app, classifier runner, OncoTree resources, and the Java classifier used by the app. Pathology report parsing is kept in the sibling `LLMPathReportParser` repository.

A publicly-hosted version of the app is hosted at http://tanlab.utah.edu:8094/. This version is limited to Ollama cloud model use and requires an API key from Ollama to access cloud models. This version also has a batch submission limit of 10 files at a time. 

**Warning**: Do not upload any PHI/PII to cloud-hosted AI models. To run the application using local models, read the instructions below.

## Repository Layout

```text
app.py                    Streamlit frontend
oncotree_runner.py        Python wrapper around the Java OncoTree classifier
batch_classify.py         Batch command-line classifier runner
evaluate_tcga_benchmark.py Benchmark evaluation script
full_oncotree.json        OncoTree display data used by the app
OT_0.3.jar                Java OncoTree classifier (from OncoTree Repo)
OTResources13July2026/    OncoTree prompts, catalogs, ICD files, and resources (from OncoTree Repo)
USeq_9.3.9/               USeq tools used for Tempus JSON parsing (TempusPathoPrinter from USeq)
```

The app expects `LLMPathReportParser` and `LLMOncoTreeApp` to be cloned next to each other:

```text
workspace/
  LLMPathReportParser/
  LLMOncoTreeApp/
```

## Requirements

- Python 3.10+
- Java 21+
- Ollama installed and running for local models
- Optional Ollama Cloud API key for cloud models

## Install

Clone both repositories into the same parent directory:

```bash
git clone https://github.com/GabrielaFort/LLMPathReportParser.git
git clone https://github.com/GabrielaFort/LLMOncoTreeApp.git
```

Create and activate a Python environment:

```bash
cd LLMOncoTreeApp
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Make the parser repository available to the app:

```bash
export PYTHONPATH="../LLMPathReportParser:$PYTHONPATH"
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

The Docker setup packages the Streamlit app, Java 21 runtime, Python dependencies, OncoTree resources, USeq resources, and the sibling `LLMPathReportParser` code into one image. Docker works the same way from macOS, Windows, or Linux as long as Docker Desktop or Docker Engine is installed.

Keep the two repositories cloned next to each other:

```text
workspace/
  LLMPathReportParser/
  LLMOncoTreeApp/
```

The Docker files live in `LLMOncoTreeApp/docker/`. From `LLMOncoTreeApp`, build and run the app locally with Compose:

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

The container does not run Ollama itself. For local models, keep Ollama running on the host machine and let the app and Java classifier connect to it through `OLLAMA_HOST`:

```text
OLLAMA_HOST=http://host.docker.internal:11434
```

This default is already set in `docker/docker-compose.yml` and the `Dockerfile`. To change it for Compose, edit the `OLLAMA_HOST` value under `environment`.

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

If Linux Docker cannot connect to Ollama on the same computer, Ollama may only be listening on `127.0.0.1`. Start Ollama on a reachable address instead:

```bash
OLLAMA_HOST=0.0.0.0:28641 ollama serve
```

Then set the app container to the matching port:

```yaml
OLLAMA_HOST: http://host.docker.internal:28641
```

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

Accepted JSON files are normalized and sent directly to the Java OncoTree classifier.

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

### Cloud Model PHI Confirmation

When a cloud model is selected, you will be asked to confirm the uploads do not contain PHI. Do not upload any PHI to a cloud-hosted LLM.

## Input JSON Format

The classifier expects one JSON record per case:

```json
{
  "icd_code_descriptions": "",
  "path_lab_info": "",
  "test_order_id": "",
  "sample_site": ""
}
```


