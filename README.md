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
git clone https://github.com/<user-or-org>/LLMPathReportParser.git
git clone https://github.com/<user-or-org>/LLMOncoTreeApp.git
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
s
- The Java classifier and USeq resources originate from the Huntsman Cancer Institute OncoTree/USeq tooling.
