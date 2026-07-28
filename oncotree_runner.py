import io
import json
import os
import subprocess
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

APP_DIR = Path(__file__).parent.resolve()
EXTERNAL_DIR = APP_DIR / ".external"
RUNTIME_DIR = EXTERNAL_DIR / "runtime"
EXTERNAL_PARSER_DIR = EXTERNAL_DIR / "LLMPathReportParser"

if EXTERNAL_PARSER_DIR.exists():
    sys.path.insert(0, str(EXTERNAL_PARSER_DIR))

from report_input_parser import (
    build_oncotree_input_json,
    bytes_to_oncotree_input as parser_bytes_to_oncotree_input,
    convert_pdf_bytes_to_md,
    extract_docx_text,
    file_path_to_oncotree_input as parser_file_path_to_oncotree_input,
    get_model_source,
    is_oncotree_input_json,
    normalize_oncotree_input_json,
    uploaded_file_to_oncotree_input as parser_uploaded_file_to_oncotree_input,
)


OT_JAR_PATH = RUNTIME_DIR / "OT.jar"
TEMPUS_PATHO_PRINTER_PATH = RUNTIME_DIR / "USeq" / "Apps" / "TempusPathoPrinter"
OT_RESOURCES_DIR = RUNTIME_DIR / "OTResources" / "OTResources13July2026"

PROMPT_TISSUE_PATH = OT_RESOURCES_DIR / "promptTissue.txt"
TISSUE_NODE_CODES_PATH = OT_RESOURCES_DIR / "tissueCodeNodeCodes.txt"
TISSUE_NODE_CATALOG_PATH = OT_RESOURCES_DIR / "TissueNodeCatalog"
ICD_DIAGNOSIS_PATH = OT_RESOURCES_DIR / "ICD" / "ICD-10_Diagnosis.txt"
ICD_MORPHOLOGY_PATH = OT_RESOURCES_DIR / "ICD" / "ICD_Morphology.txt"
ICD_TOPOLOGY_PATH = OT_RESOURCES_DIR / "ICD" / "ICD_Topology.txt"
RESULTS_DIR = APP_DIR / "results"
DEFAULT_OLLAMA_HOST = "http://localhost:11434"

TEMPUS_V33_MARKER_FIELDS = ["metadata", "rna", "ihc"]
JSON_INPUT_AUTO = "auto"
JSON_INPUT_ONCOTREE = "oncotree"
JSON_INPUT_TEMPUS = "tempus"
JSON_INPUT_TYPES = {JSON_INPUT_AUTO, JSON_INPUT_ONCOTREE, JSON_INPUT_TEMPUS}


def safe_case_id(case_id):
    return "".join(
        char if char.isalnum() or char in ["_", "-", "."] else "_"
        for char in str(case_id)
    )


def is_tempus_v33_json(parsed):
    return isinstance(parsed, dict) and any(field in parsed for field in TEMPUS_V33_MARKER_FIELDS)


def describe_json_input_type(parsed):
    if is_oncotree_input_json(parsed):
        return JSON_INPUT_ONCOTREE
    if is_tempus_v33_json(parsed):
        return JSON_INPUT_TEMPUS
    return None


def get_ollama_base_url(ollama_host=None):
    base_url = (
        ollama_host
        or os.environ.get("OLLAMA_HOST")
        or DEFAULT_OLLAMA_HOST
    ).strip()
    if not base_url:
        base_url = DEFAULT_OLLAMA_HOST
    if not base_url.startswith(("http://", "https://")):
        base_url = f"http://{base_url}"
    return base_url


def tempus_json_to_oncotree_input(file_bytes, filename):
    if not TEMPUS_PATHO_PRINTER_PATH.exists():
        raise FileNotFoundError(f"TempusPathoPrinter not found: {TEMPUS_PATHO_PRINTER_PATH}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        input_dir = temp_dir / "tempus_json"
        output_dir = temp_dir / "oncotree_input"
        input_dir.mkdir()
        output_dir.mkdir()

        input_path = input_dir / Path(filename).name
        input_path.write_bytes(file_bytes)

        command = [
            "java",
            "-jar",
            str(TEMPUS_PATHO_PRINTER_PATH),
            "-j",
            str(input_dir),
            "-s",
            str(output_dir),
            "-i",
            str(ICD_DIAGNOSIS_PATH),
            "-m",
            str(ICD_MORPHOLOGY_PATH),
            "-t",
            str(ICD_TOPOLOGY_PATH),
            "-r",
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            raise RuntimeError(result.stderr or result.stdout or "TempusPathoPrinter failed.")

        for output_path in sorted(output_dir.rglob("*.json")):
            parsed = json.loads(output_path.read_text(encoding="utf-8"))
            if is_oncotree_input_json(parsed):
                return normalize_oncotree_input_json(parsed, filename)

    raise RuntimeError("TempusPathoPrinter completed, but no OncoTree input JSON was found.")


def read_json_bytes(file_bytes, filename, json_input_type=JSON_INPUT_AUTO):
    if json_input_type not in JSON_INPUT_TYPES:
        raise ValueError(f"Unknown JSON input type: {json_input_type}")

    parsed = json.loads(file_bytes.decode("utf-8"))

    if json_input_type == JSON_INPUT_ONCOTREE:
        if not is_oncotree_input_json(parsed):
            raise ValueError("Selected OncoTree input JSON, but required fields were not found.")
        return normalize_oncotree_input_json(parsed, filename)

    if json_input_type == JSON_INPUT_TEMPUS:
        if not is_tempus_v33_json(parsed):
            raise ValueError("Selected Tempus v3.3+ report JSON, but expected Tempus fields were not found.")
        return tempus_json_to_oncotree_input(file_bytes, filename)

    detected_type = describe_json_input_type(parsed)
    if detected_type == JSON_INPUT_ONCOTREE:
        return normalize_oncotree_input_json(parsed, filename)

    if detected_type == JSON_INPUT_TEMPUS:
        return tempus_json_to_oncotree_input(file_bytes, filename)

    raise ValueError("JSON must be OncoTree input JSON or Tempus v3.3+ JSON.")


def uploaded_file_to_oncotree_input(
    uploaded_file,
    parser_model,
    model_source=None,
    api_key=None,
    pdf_text_getter=None,
    ollama_host=None,
    json_input_type=JSON_INPUT_AUTO,
):
    if Path(uploaded_file.name).suffix.lower() == ".json":
        return read_json_bytes(uploaded_file.getvalue(), uploaded_file.name, json_input_type)

    return parser_uploaded_file_to_oncotree_input(
        uploaded_file,
        parser_model,
        model_source=model_source,
        api_key=api_key,
        pdf_text_getter=pdf_text_getter,
        ollama_host=ollama_host,
    )


def bytes_to_oncotree_input(
    filename,
    file_bytes,
    parser_model,
    model_source=None,
    api_key=None,
    pdf_text_getter=None,
    ollama_host=None,
    json_input_type=JSON_INPUT_AUTO,
):
    suffix = Path(filename).suffix.lower()

    if suffix == ".json":
        return read_json_bytes(file_bytes, filename, json_input_type)

    return parser_bytes_to_oncotree_input(
        filename,
        file_bytes,
        parser_model,
        model_source,
        api_key,
        pdf_text_getter=pdf_text_getter,
        ollama_host=ollama_host,
    )


def file_path_to_oncotree_input(
    path,
    parser_model,
    model_source=None,
    api_key=None,
    ollama_host=None,
    json_input_type=JSON_INPUT_AUTO,
):
    path = Path(path)
    if path.suffix.lower() == ".json":
        return read_json_bytes(path.read_bytes(), path.name, json_input_type)

    return parser_file_path_to_oncotree_input(
        path,
        parser_model,
        model_source,
        api_key,
        ollama_host=ollama_host,
    )


def run_oncotree_classifier(
    input_record,
    selected_model,
    selected_model_source=None,
    api_key=None,
    context_size=24000,
    persist_results=False,
    ollama_host=None,
):
    selected_model_source = selected_model_source or get_model_source(selected_model)
    ollama_host = get_ollama_base_url(ollama_host)
    case_id = input_record.get("test_order_id") or f"case_{uuid.uuid4().hex[:8]}"
    safe_id = safe_case_id(case_id)

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_dir = Path(temp_dir)
        results_dir = RESULTS_DIR / safe_id if persist_results else temp_dir / "results" / safe_id
        results_dir.mkdir(parents=True, exist_ok=True)

        input_dir = Path(temp_dir) / safe_id
        input_dir.mkdir(parents=True, exist_ok=True)

        input_json_path = input_dir / f"{safe_id}.json"
        with open(input_json_path, "w", encoding="utf-8") as f:
            json.dump(input_record, f, indent=2)

        command = [
            "java",
            "-jar",
            str(OT_JAR_PATH),
            "Classifier",
            "-m",
            selected_model,
            "-c",
            str(context_size),
            "-t",
            str(PROMPT_TISSUE_PATH),
            "-n",
            str(TISSUE_NODE_CODES_PATH),
            "-a",
            str(TISSUE_NODE_CATALOG_PATH),
            "-j",
            str(input_dir),
            "-r",
            str(results_dir),
            "-h",
            ollama_host,
        ]

        if selected_model_source == "cloud":
            if not api_key:
                raise ValueError("Ollama Cloud API key is required for cloud models.")
            command.extend(["-k", api_key])

        result = subprocess.run(command, capture_output=True, text=True, check=False)

        output_files = {}
        for path in results_dir.rglob("*"):
            if not path.is_file():
                continue
            display_name = str(path.relative_to(results_dir))
            try:
                output_files[display_name] = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                output_files[display_name] = path.read_bytes()

    return {
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "output_files": output_files,
    }


def zip_output_files(output_files, case_id="oncotree_results"):
    buffer = io.BytesIO()
    safe_id = safe_case_id(case_id or "oncotree_results")

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for filename, contents in output_files.items():
            file_bytes = contents.encode("utf-8") if isinstance(contents, str) else contents
            zip_file.writestr(f"{safe_id}/{filename}", file_bytes)

    buffer.seek(0)
    return buffer


def zip_batch_output_files(batch_results):
    buffer = io.BytesIO()

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for item in batch_results:
            if item.get("error") or not item.get("input_record") or not item.get("result"):
                continue

            case_id = item["input_record"].get("test_order_id") or item.get("filename") or "oncotree_results"
            safe_id = safe_case_id(case_id)

            for filename, contents in item["result"].get("output_files", {}).items():
                file_bytes = contents.encode("utf-8") if isinstance(contents, str) else contents
                zip_file.writestr(f"{safe_id}/{filename}", file_bytes)

    buffer.seek(0)
    return buffer
