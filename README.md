# LLM OncoTree App

Streamlit app and command-line utilities for running the LLM OncoTree classifier.

This repository contains the app, classifier runner, benchmark script, OncoTree resources, and the Java classifier used by the app. Pathology report parsing is kept in the sibling `LLMPathReportParser` repository.

## Repository Layout

```text
app.py                    Streamlit frontend
oncotree_runner.py        Python wrapper around the Java OncoTree classifier
batch_classify.py         Batch command-line classifier runner
evaluate_tcga_benchmark.py Benchmark evaluation script
full_oncotree.json        OncoTree display data used by the app
OT_0.3.jar                Java OncoTree classifier
OTResources13July2026/    OncoTree prompts, catalogs, ICD files, and resources
USeq_9.3.9/               USeq tools used for Tempus JSON parsing
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

From `LLMOncoTreeApp`, build and run the app:

```bash
docker compose up --build
```

Then open:

```text
http://localhost:8501
```

To stop the app:

```bash
docker compose down
```

### Docker And Ollama

The container does not run Ollama itself. For local models, keep Ollama running on the host machine and let the app and Java classifier connect to it through:

```text
OLLAMA_HOST=http://host.docker.internal:11434
```

This is already set in `docker-compose.yml` and the `Dockerfile`.

On macOS and Windows with Docker Desktop, `host.docker.internal` is usually available automatically. On Linux, `docker-compose.yml` adds `host.docker.internal:host-gateway`; if Ollama only listens on `127.0.0.1`, you may also need to start Ollama so it listens on an address reachable from Docker, such as `0.0.0.0`.

If classifier logs show `-h Host http://localhost:11434` inside Docker, the container is not receiving or forwarding `OLLAMA_HOST` correctly. It should show `http://host.docker.internal:11434` when using the included Docker configuration.

Ollama Cloud models do not require a local Ollama server, but the app still requires an Ollama Cloud API key before cloud model classification.

## Accepted Inputs And Behavior

The Streamlit app has three input modes:

- **File Upload** accepts one `.pdf`, `.txt`, `.docx`, or `.json` file.
- **Form Upload** accepts manual text entry and does not require a document upload.
- **Batch Upload** accepts multiple `.pdf`, `.txt`, `.docx`, and `.json` files.

Uploaded report files are handled as follows:

- `.pdf` files are displayed in the app and converted to text before parsing.
- `.txt` files are read as UTF-8 text, with invalid characters replaced.
- `.docx` files are converted to text before parsing.
- `.json` files must be either OncoTree input JSON or Tempus v3.3+ JSON.

For `.pdf`, `.txt`, and `.docx` files, the selected LLM is used first to parse the report into the OncoTree input JSON fields, then the Java OncoTree classifier runs on that JSON. For accepted `.json` files, the app skips report parsing and sends the normalized JSON directly to the classifier.

When a cloud model is selected, the PHI confirmation appears before document upload. File and batch upload controls are disabled until the user confirms there is no PHI present, so documents cannot be successfully uploaded for cloud processing before that confirmation. The same PHI confirmation is required before manual form classification with a cloud model.

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

Use `LLMPathReportParser` to prepare these JSON files from pathology reports without running the classifier.

## Batch Classification

```bash
export PYTHONPATH="../LLMPathReportParser:$PYTHONPATH"
python batch_classify.py --input input_json --model llama3.1
```

For Ollama Cloud models:

```bash
python batch_classify.py \
  --input input_json \
  --model gemma4:31b-cloud \
  --api-key-file key.txt
```

## Notes
- The Java classifier and USeq resources originate from the Huntsman Cancer Institute OncoTree/USeq tooling.
