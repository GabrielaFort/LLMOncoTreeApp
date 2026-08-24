import streamlit as st
import streamlit.components.v1 as components
import ollama
import requests
import base64
import io
import os
from pathlib import Path
import html
import json
import uuid
from urllib.parse import urlencode
from pypdf import PdfReader, PdfWriter
from app_logging import setup_vm_logging
from oncotree_runner import (
    APP_DIR,
    build_oncotree_input_json,
    convert_pdf_bytes_to_md,
    describe_json_input_type,
    extract_docx_text,
    get_ollama_base_url,
    JSON_INPUT_AUTO,
    JSON_INPUT_ONCOTREE,
    JSON_INPUT_TEMPUS,
    run_oncotree_classifier,
    uploaded_file_to_oncotree_input as runner_uploaded_file_to_oncotree_input,
    zip_batch_output_files,
    zip_output_files,
)

ONCOTREE_BASE_URL = "https://oncotree.mskcc.org/"
FULL_ONCOTREE_JSON_PATH = APP_DIR / "full_oncotree.json"
CLOUD_PHI_WARNING = "Warning: You are about to submit your file(s) to a cloud hosted AI model. Please ensure there is no PHI present before submission"
DEFAULT_PDF_PAGE_LIMIT = 5
RUN_ENVIRONMENT = os.environ.get("RUN_ENVIRONMENT", "LOCAL").strip().upper()
IS_VM_ENVIRONMENT = RUN_ENVIRONMENT == "VM"
try:
    VM_BATCH_FILE_LIMIT = int(os.environ.get("VM_BATCH_FILE_LIMIT", "10"))
except ValueError:
    VM_BATCH_FILE_LIMIT = 10

RECOMMENDED_CLOUD_MODELS = ["glm-5.2", "gemma4:31b"]
RECOMMENDED_LOCAL_MODELS = ["gemma4:e4b", "gemma4:26b"]

DEMO_FORM_INPUT = {
    "test_order_id": "12345",
    "sample_site": "Lung, lower lobe",
    "sample_type": "Primary tumor, Grade 3",
    "path_lab_info": "Squamous cell carcinoma",
    "icd_code_descriptions": "Carcinoma, Squamous Cell, NOS",
    "other_comments": "Invasive, poorly differentiated squamous cell carcinoma with cellular and nuclear atypia. p40 positive by IHC.",
}

JSON_INPUT_TYPE_OPTIONS = {
    "Auto-detect": JSON_INPUT_AUTO,
    "OncoTree classifier input JSON": JSON_INPUT_ONCOTREE,
    "Tempus v3.3+ report JSON": JSON_INPUT_TEMPUS,
}

JSON_INPUT_TYPE_LABELS = {
    JSON_INPUT_AUTO: "Auto-detect",
    JSON_INPUT_ONCOTREE: "OncoTree classifier input JSON",
    JSON_INPUT_TEMPUS: "Tempus v3.3+ report JSON",
    None: "Unknown JSON type",
}

st.set_page_config(page_title = "LLM OncoTree Classifier", layout = "wide", initial_sidebar_state = "expanded")

# Add custom CSS for styled tabs
st.markdown("""
<style>
    .block-container {
        max-width: 1400px;
        padding-top: 2.75rem;
        padding-left: 3rem;
        padding-right: 3rem;
    }

    .app-header {
        text-align: center;
        background: #e2e8f0;
        border: 2px solid #64748b;
        border-radius: 8px;
        padding: 1.35rem 1.5rem;
        margin-top: 0.25rem;
        margin-bottom: 1.25rem;
    }

    .app-header h1 {
        margin: 0 0 0.35rem 0;
        font-size: 2.25rem;
        line-height: 1.15;
    }

    .app-header p {
        color: #64748b;
        margin: 0.25rem 0;
        font-size: 0.98rem;
    }

    .app-header a {
        color: #334155;
        text-decoration: none;
        font-weight: 600;
    }

    .app-header a:hover {
        color: #0f766e;
        text-decoration: underline;
    }

    /* Style the tab buttons. */
    div[data-testid="stTabs"] div[role="tablist"] {
        width: 100%;
        gap: 8px !important;
        background-color: transparent !important;
        padding: 4px 0 8px 0 !important;
    }

    div[data-testid="stTabs"] button[role="tab"] {
        flex: 1 1 0 !important;
        justify-content: center !important;
        height: 48px !important;
        min-height: 48px !important;
        background-color: #e2e8f0 !important;
        border-radius: 8px 8px 0 0 !important;
        padding: 10px 20px !important;
        font-weight: 600 !important;
        border: 2px solid #64748b !important;
        border-bottom: none !important;
        transition: background-color 0.2s ease, border-color 0.2s ease !important;
    }

    div[data-testid="stTabs"] button[role="tab"]:hover {
        background-color: #dbe4ee !important;
        border-color: #475569 !important;
    }

    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        background-color: #ffffff !important;
        border-color: #475569 !important;
        border-bottom: 2px solid #ffffff !important;
        box-shadow: 0 -1px 6px rgba(15, 23, 42, 0.08) !important;
    }

    div[data-testid="stTabs"] button[role="tab"] p {
        font-size: 1rem !important;
        font-weight: 600 !important;
        margin: 0 !important;
        line-height: 1.2 !important;
        white-space: nowrap !important;
    }

	</style>
""", unsafe_allow_html=True)

st.markdown(
    """
    <div class="app-header">
        <h1>LLM OncoTree Classifier</h1>
        <p>Prepare pathology reports or JSON records and run the OncoTree classifier.</p>
        <p>Documentation: <a href="https://github.com/GabrielaFort/LLMOncoTreeApp" target="_blank">LLMOncoTreeApp</a> and <a href="https://github.com/HuntsmanCancerInstitute/OncoTree/tree/master" target="_blank">OncoTree</a></p>

    </div>
    """,
    unsafe_allow_html=True,
)

with st.expander("What can I upload?", expanded=False):
    st.markdown(
        """
        - PDF, TXT, or DOCX pathology reports (parsed into OncoTree input JSON before classification using [LLMPathReportParser](https://github.com/GabrielaFort/LLMPathReportParser)).
        - OncoTree classifier input JSON (sent directly to the classifier).
        - Tempus v3.3+ report JSON (parsed into OncoTree input JSON before classification using [TempusPathoPrinter](https://github.com/HuntsmanCancerInstitute/USeq))
        """
    )

st.warning("**Warning:** Do not upload any PHI/PII to cloud-hosted AI models or unapproved systems. See the documentation for instructions on using local models.")

# Initiate logging
logger = setup_vm_logging(IS_VM_ENVIRONMENT)

# Log new sessions in VM mode
if IS_VM_ENVIRONMENT:
    if "session_id" not in st.session_state:
        st.session_state["session_id"] = str(uuid.uuid4())
        st.session_state["rerun_count"] = 0
        logger.info("NEW SESSION session_id=%s", st.session_state["session_id"])
    else:
        st.session_state["rerun_count"] += 1
        logger.info(
            "RERUN session_id=%s rerun count=%s",
            st.session_state["session_id"],
            st.session_state["rerun_count"],
        )

# Function to auto-detect local LLMs on machine, assuming Ollama is running
def discover_local_ollama_models():
    """
    Return a sorted list of model names from ollama.list()
    """
    try:
        models = ollama.Client(host=get_ollama_base_url()).list()["models"]
    except Exception as e:
        # Ollama client not available or not running
        # Return an empty list
        return []
    
    names = []
    for model in models:
        # each m has attribute model
        if hasattr(model, "model"):
            names.append(model.model)
        elif isinstance(model, dict) and "model" in model:
            names.append(model["model"])

    return sorted(set(names))


# Function to return all available ollama cloud models
def discover_ollama_cloud_models():
    """
    Return a sorted list of model names from ollama cloud
    """
    try:
        response = requests.get("https://ollama.com/api/tags", timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        # Error loading models
        print(f'Could not load Ollama cloud models: {e}')
        return []
    
    models = data.get("models", [])
    
    names = []

    for model in models:
        if isinstance(model, dict):
            name = model.get("model")
            if name:
                names.append(name)
    
    return sorted(set(names))

# Helper function to display results in a user-friendly way
def display_classifier_result(
    result,
    key_prefix="result",
    show_oncotree=True,
    download_case_id=None,
    show_download_zip=True,
    show_output_files=True,
):
    if result["returncode"] != 0:
        st.error("Classifier failed.")

        if result["stderr"]:
            with st.expander("Error log", expanded=True):
                st.code(result["stderr"])

        if result["stdout"]:
            with st.expander("Classifier output", expanded=False):
                st.code(result["stdout"])

        return

    st.success("Classification complete.")

    if result["stdout"]:
        with st.expander("Classifier log", expanded=False):
            st.code(result["stdout"])

    if not result["output_files"]:
        st.warning("Classifier completed, but no output files were found.")
        return

    display_classification_summary(result["output_files"])
    if show_oncotree:
        display_oncotree_tree(result["output_files"], key_prefix)

    if not show_output_files:
        return

    st.markdown("**Output files**")
    if show_download_zip:
        download_case_id = download_case_id or key_prefix
        st.download_button(
            "Download results ZIP",
            data=zip_output_files(result["output_files"], download_case_id),
            file_name=f"{download_case_id}_oncotree_results.zip",
            mime="application/zip",
            key=f"{key_prefix}_download_results_zip",
        )

    for filename, contents in result["output_files"].items():
        file_bytes = contents.encode("utf-8") if isinstance(contents, str) else contents
        file_size = len(file_bytes)

        with st.expander(f"{filename} ({file_size:,} bytes)", expanded=False):
            if isinstance(contents, str):
                st.code(contents)
            else:
                st.write("Binary output file")


def get_classification_json(output_files, file_prefix):
    for filename, contents in output_files.items():
        if filename.startswith(file_prefix) and isinstance(contents, str):
            try:
                return json.loads(contents)
            except json.JSONDecodeError:
                return None
    return None


def confidence_style(confidence):
    normalized = str(confidence).strip().lower()

    if normalized.startswith("high"):
        return "#dcfce7", "#166534"
    if normalized.startswith("med"):
        return "#fef9c3", "#854d0e"
    if normalized.startswith("low"):
        return "#fee2e2", "#991b1b"

    return "#f1f5f9", "#334155"


def render_confidence_box(confidence):
    background, color = confidence_style(confidence)
    safe_confidence = html.escape(str(confidence))

    st.markdown(
        f"""
        <div style="font-size:0.875rem;color:#64748b;margin-bottom:0.25rem;">Confidence</div>
        <div style="background:{background};color:{color};border:1px solid {color};border-radius:6px;padding:0.45rem 0.65rem;font-weight:700;text-align:center;">
            {safe_confidence}
        </div>
        """,
        unsafe_allow_html=True,
    )


def display_classification_summary(output_files):
    summary_specs = [
        ("TissueClassified", "TissueClassified/", "oncotree_tissue_code"),
        ("NodeClassified", "NodeClassified/", "oncotree_code"),
    ]

    st.markdown("**Classification results**")

    for title, file_prefix, code_field in summary_specs:
        result_json = get_classification_json(output_files, file_prefix)

        if not result_json:
            continue

        code = result_json.get(code_field, "Not reported")
        confidence = result_json.get("confidence", "Not reported")
        reasoning = result_json.get("reasoning", "No reasoning reported.")

        with st.expander(title, expanded=True):
            code_col, confidence_col = st.columns(2)
            code_col.metric("OncoTree code", code)
            with confidence_col:
                render_confidence_box(confidence)

            st.markdown("**Reasoning**")
            st.write(reasoning)


def get_oncotree_result_code(output_files):
    tissue_result = get_classification_json(output_files, "TissueClassified/")
    node_result = get_classification_json(output_files, "NodeClassified/")

    tissue_code = tissue_result.get("oncotree_tissue_code") if tissue_result else None
    node_code = node_result.get("oncotree_code") if node_result else None
    return node_code or tissue_code


@st.cache_data
def load_oncotree_code_names():
    nodes = json.loads(FULL_ONCOTREE_JSON_PATH.read_text(encoding="utf-8"))
    return {
        node["code"]: node["name"]
        for node in nodes
        if node.get("code") and node.get("name")
    }


def get_oncotree_url(output_files):
    result_code = get_oncotree_result_code(output_files)
    if not result_code:
        return None

    result_name = load_oncotree_code_names().get(result_code)
    search_field = "NAME" if result_name else "CODE"
    search_value = f"{result_name} ({result_code})" if result_name else result_code

    return f"{ONCOTREE_BASE_URL}?{urlencode({'version': 'oncotree_latest_stable', 'field': search_field, 'search': search_value})}"


def display_oncotree_tree(output_files, key_prefix):
    oncotree_url = get_oncotree_url(output_files)

    if not oncotree_url:
        return

    st.subheader("OncoTree Visualization")
    if hasattr(st, "iframe"):
        st.iframe(oncotree_url, height=800)
    else:
        components.iframe(oncotree_url, height=800)


# Model validation helper
def validate_model_selection():
    if st.session_state.selected_model is None:
        st.error("Please select a model before running classification.")
        return False

    if (
        st.session_state.selected_model_source == "cloud"
        and not st.session_state.ollama_cloud_api_key
    ):
        st.error("Please enter an Ollama Cloud API key before using a cloud model.")
        return False

    return True


def confirm_cloud_submission(key):
    if st.session_state.selected_model_source != "cloud":
        return True

    st.warning(CLOUD_PHI_WARNING)
    return st.checkbox(
        "I confirm there is no PHI present.",
        key=key,
    )


def cloud_uploads_allowed(key):
    confirmed = confirm_cloud_submission(key)
    if not confirmed:
        st.info("Confirm there is no PHI present before uploading documents for a cloud model.")

    return confirmed


def upload_widget_key(base_key, cloud_confirmed):
    if st.session_state.selected_model_source == "cloud":
        return f"{base_key}_cloud_allowed" if cloud_confirmed else f"{base_key}_cloud_blocked"

    return f"{base_key}_local"


def upload_widget_disabled(cloud_confirmed):
    return st.session_state.selected_model_source == "cloud" and not cloud_confirmed


# LLM settings sidebar
st.sidebar.header("LLM Settings")
if IS_VM_ENVIRONMENT:
    with st.sidebar.expander("Model setup", expanded=False):
        st.markdown(
            """
            - This public web version of OncoTree.AI only supports Ollama cloud models. Cloud models require an Ollama cloud API key and should not be used with PHI.
            - To use local Ollama models, follow the manual or Docker installation instructions [here](https://github.com/GabrielaFort/LLMOncoTreeApp)
            """
        )

else:
    with st.sidebar.expander("Model setup", expanded=False):
        st.markdown(
            """
            - For local models, start Ollama normally. The app uses Ollama's default host unless `OLLAMA_HOST` is set.
            - Docker uses `http://host.docker.internal:11434` by default.
            - Cloud models require an Ollama Cloud API key and should not be used with PHI.
            """
        )

available_local_models = [] if IS_VM_ENVIRONMENT else discover_local_ollama_models()

# Show sidebar message if no local models are found
if not IS_VM_ENVIRONMENT and not available_local_models:
    st.sidebar.warning("No local LLMs detected. Ensure Ollama is running and models are available.")

# Initialize cloud model storage and settings
if "available_cloud_models" not in st.session_state:
    st.session_state.available_cloud_models = []
if "ollama_cloud_api_key" not in st.session_state:
    st.session_state.ollama_cloud_api_key = ""

# Optional cloud model setup
cloud_label = "Optional: Use Ollama Cloud Models" if not IS_VM_ENVIRONMENT else "Enter Ollama Cloud API Key to Load Models"
with st.sidebar.expander(cloud_label, expanded=False):
    api_key = st.text_input("Ollama Cloud API Key", type="password", value = st.session_state.ollama_cloud_api_key)
    st.session_state.ollama_cloud_api_key = api_key  # Store the API key in session state

    if st.button("Load cloud models"):
        if not api_key:
            st.warning("Please enter your Ollama Cloud API Key to load cloud models.")
        else:
            st.session_state.available_cloud_models = discover_ollama_cloud_models()
            if st.session_state.available_cloud_models:
                st.success(f"Loaded {len(st.session_state.available_cloud_models)} cloud models.")
            else:
                st.warning("No cloud models found.")

model_options = [("No model selected", None, None)]
model_options.extend(
    (f"Local: {model}", model, "local")
    for model in sorted(set(available_local_models))
)
model_options.extend(
    (f"Cloud: {model}", model, "cloud")
    for model in sorted(set(st.session_state.available_cloud_models))
)

def format_model_option(option):
    label, model, source = option
    if (
        (source == "local" and model in RECOMMENDED_LOCAL_MODELS)
        or (source == "cloud" and model in RECOMMENDED_CLOUD_MODELS)
    ):
        return f"* {label} (recommended)"
    return label

if st.session_state.get("selected_model_option") not in model_options:
    st.session_state.selected_model_option = model_options[0]

selected_model_option = st.sidebar.selectbox(
    "Select Model",
    options=model_options,
    index=0,
    key="selected_model_option",
    format_func=format_model_option,
)

if IS_VM_ENVIRONMENT:
    st.sidebar.caption(f"Recommended Cloud Models: {', '.join(RECOMMENDED_CLOUD_MODELS)}")
else:
    st.sidebar.caption(
        f"Recommended Local Models: {', '.join(RECOMMENDED_LOCAL_MODELS)}"
    )
    st.sidebar.caption(
        f"Recommended Cloud Models: {', '.join(RECOMMENDED_CLOUD_MODELS)}"
    )
    
_, selected_model, selected_model_source = selected_model_option

st.session_state.selected_model = selected_model
st.session_state.selected_model_source = selected_model_source

if selected_model is None:
    st.sidebar.info("Select a model before running classification.")
else:
    st.sidebar.success(f"Selected {selected_model_source} model: {selected_model}")

if "file_classifier_result" not in st.session_state:
    st.session_state.file_classifier_result = None
if "file_input_record" not in st.session_state:
    st.session_state.file_input_record = None
if "form_classifier_result" not in st.session_state:
    st.session_state.form_classifier_result = None
if "form_input_record" not in st.session_state:
    st.session_state.form_input_record = None
if "batch_results" not in st.session_state:
    st.session_state.batch_results = None

# Tabs for file, form, or batch upload
file_tab, form_tab, batch_tab = st.tabs(["File Upload", "Form Upload", "Batch Upload"])

# PDF viewer function 
def render_pdf(pdf_bytes, height=700):
    base64_pdf = base64.b64encode(pdf_bytes).decode("utf-8")
    pdf_display = f"""
        <iframe
            src="data:application/pdf;base64,{base64_pdf}"
            width="100%"
            height="{height}"
            type="application/pdf">
        </iframe>
    """
    st.markdown(pdf_display, unsafe_allow_html=True)

def first_pdf_pages(pdf_bytes, page_limit=DEFAULT_PDF_PAGE_LIMIT):
    if page_limit < 1:
        raise ValueError("PDF page limit must be at least 1.")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()

    for index, page in enumerate(reader.pages):
        if index >= page_limit:
            break
        writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def count_pdf_pages(pdf_bytes):
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


def get_uploaded_pdf_md(uploaded_file, page_limit=DEFAULT_PDF_PAGE_LIMIT):
    cache_key = f"{uploaded_file.name}:{getattr(uploaded_file, 'size', '')}:{page_limit}"

    if st.session_state.get("uploaded_pdf_md_key") != cache_key:
        st.session_state.uploaded_pdf_md_key = cache_key
        st.session_state.uploaded_pdf_md = convert_pdf_bytes_to_md(
            uploaded_file.getvalue(),
            page_limit=page_limit,
        )

    return st.session_state.uploaded_pdf_md


def uploaded_file_to_oncotree_input(
    uploaded_file,
    json_input_type=JSON_INPUT_AUTO,
    pdf_page_limit=None,
):
    pdf_page_limit = pdf_page_limit or DEFAULT_PDF_PAGE_LIMIT

    return runner_uploaded_file_to_oncotree_input(
        uploaded_file,
        st.session_state.selected_model,
        st.session_state.selected_model_source,
        st.session_state.ollama_cloud_api_key,
        pdf_text_getter=lambda file: get_uploaded_pdf_md(file, pdf_page_limit),
        json_input_type=json_input_type,
    )


# File upload tab
with file_tab:
    st.subheader("Classify from uploaded file")
    st.caption("Use this for one pathology report, one OncoTree input JSON, or one Tempus v3.3+ report JSON.")

    file_cloud_confirmed = cloud_uploads_allowed("file_cloud_phi_confirm")
    uploaded_file = st.file_uploader("Upload pathology report or test result",
                                     type = ["txt", "pdf", "docx", "json"],
                                     key = upload_widget_key("uploaded_report_file", file_cloud_confirmed),
                                     disabled = upload_widget_disabled(file_cloud_confirmed))
    file_json_input_type = JSON_INPUT_AUTO
    file_pdf_page_limit = DEFAULT_PDF_PAGE_LIMIT
    if uploaded_file is not None:
        upload_token = f"{uploaded_file.name}:{getattr(uploaded_file, 'size', '')}"
        if st.session_state.get("file_logged_upload_token") != upload_token:
            st.session_state.file_logged_upload_token = upload_token
            logger.info(
                "FILE_UPLOADED session_id=%s input_mode=file",
                st.session_state.get("session_id"),
            )

        uploaded_bytes = uploaded_file.getvalue()
        st.success(f"Loaded file: {uploaded_file.name}")

        if uploaded_file.name.lower().endswith(".pdf"):
            file_pdf_page_limit = st.number_input(
                "PDF pages to process",
                min_value=1,
                value=DEFAULT_PDF_PAGE_LIMIT,
                step=1,
                help = "Diagnosis information is often in the first few pages. Fewer pages usually means faster processing.",
                key="file_pdf_page_limit",
            )

        if uploaded_file.name.lower().endswith(".json"):
            file_json_label = st.radio(
                "JSON type",
                options=list(JSON_INPUT_TYPE_OPTIONS),
                horizontal=True,
                help="Auto-detect works for most files. Choose explicitly if the app cannot infer the JSON type.",
                key="file_json_input_type_label",
            )
            file_json_input_type = JSON_INPUT_TYPE_OPTIONS[file_json_label]

        with st.expander("Preview uploaded file", expanded=False):
            if uploaded_file.name.lower().endswith(".pdf"):
                pdf_page_count = count_pdf_pages(uploaded_bytes)
                if file_pdf_page_limit < pdf_page_count:
                    st.caption(f"Previewing first {file_pdf_page_limit} of {pdf_page_count} pages.")
                render_pdf(first_pdf_pages(uploaded_bytes, file_pdf_page_limit), height=800)

            elif uploaded_file.name.lower().endswith(".txt"):
                text = uploaded_bytes.decode("utf-8", errors="replace")
                st.text_area(
                    "Text preview",
                    value=text,
                    height=400,
                    disabled=True,
                    key="uploaded_txt_preview"
                )

            elif uploaded_file.name.lower().endswith(".docx"):
                try:
                    docx_text = extract_docx_text(uploaded_bytes)
                    st.text_area(
                        "DOCX preview",
                        value=docx_text if docx_text else "No readable text found in the DOCX file.",
                        height=400,
                        disabled=True,
                        key="uploaded_docx_preview"
                    )
                except Exception as e:
                    logger.error(
                        "DOCX_PREVIEW_ERROR session_id=%s input_mode=file error_type=%s",
                        st.session_state.get("session_id"),
                        type(e).__name__,
                    )
                    st.error(f"Error loading DOCX file: {e}")
            
            elif uploaded_file.name.lower().endswith(".json"):
                try:
                    preview_json = json.loads(uploaded_bytes.decode("utf-8"))
                    detected_type = describe_json_input_type(preview_json)
                    st.caption(f"Detected JSON type: {JSON_INPUT_TYPE_LABELS[detected_type]}")
                    st.json(preview_json)
                except Exception as e:
                    logger.error(
                        "JSON_PREVIEW_ERROR session_id=%s input_mode=file error_type=%s",
                        st.session_state.get("session_id"),
                        type(e).__name__,
                    )
                    st.error(f"Error loading JSON file: {e}")
                
        
    if st.button("Classify", key = "classify_file"):
        input_record = None

        if not validate_model_selection():
            pass
        elif not file_cloud_confirmed:
            st.error("Please confirm there is no PHI present before using a cloud model.")
        elif uploaded_file is None:
            st.error("Please upload a file before running classification.")
        else:
            try:
                with st.spinner("Preparing uploaded file..."):
                    input_record = uploaded_file_to_oncotree_input(
                        uploaded_file,
                        json_input_type=file_json_input_type,
                        pdf_page_limit=file_pdf_page_limit,
                    )

            except Exception as e:
                logger.error(
                    "FILE_PROCESSING_ERROR session_id=%s input_mode=file error_type=%s",
                    st.session_state.get("session_id"),
                    type(e).__name__,
                )
                st.error(f"Error processing uploaded file: {e}")

        if input_record is not None:
            with st.spinner("Running OncoTree classifier..."):
                result = run_oncotree_classifier(
                    input_record=input_record,
                    selected_model=st.session_state.selected_model,
                    selected_model_source=st.session_state.selected_model_source,
                    api_key=st.session_state.ollama_cloud_api_key,
                )
                if result["returncode"] != 0:
                    logger.error(
                        "CLASSIFIER_ERROR session_id=%s input_mode=file returncode=%s",
                        st.session_state.get("session_id"),
                        result["returncode"],
                    )

            st.session_state.file_input_record = input_record
            st.session_state.file_classifier_result = result

    if st.session_state.file_classifier_result is not None:
        with st.expander("Input JSON sent to classifier", expanded=False):
            st.json(st.session_state.file_input_record)

        display_classifier_result(
            st.session_state.file_classifier_result,
            key_prefix="file",
            download_case_id=st.session_state.file_input_record.get("test_order_id"),
        )


with form_tab:
    st.subheader("Classify from manual form entry")
    form_cloud_confirmed = confirm_cloud_submission("form_cloud_phi_confirm")

    if st.button("Run demo example", key="run_demo_form"):
        st.session_state.form_test_order_id = DEMO_FORM_INPUT["test_order_id"]
        st.session_state.form_sample_site = DEMO_FORM_INPUT["sample_site"]
        st.session_state.form_sample_type = DEMO_FORM_INPUT["sample_type"]
        st.session_state.form_path_lab_info = DEMO_FORM_INPUT["path_lab_info"]
        st.session_state.form_icd_code_descriptions = DEMO_FORM_INPUT["icd_code_descriptions"]
        st.session_state.form_other_comments = DEMO_FORM_INPUT["other_comments"]
        st.session_state.submit_demo_form = True

    test_order_id = st.text_input(
    "Case ID / test order ID (random ID will be generated if left blank)",
    placeholder="Example: 12345",
    key="form_test_order_id",
    )

    sample_site = st.text_input(
        "Sample site: Where the tumor sample was collected",
        placeholder="Example: Lung, lower lobe",
        key="form_sample_site",
    )

    sample_type = st.text_input(
        "Sample Type (Optional): Primary, Metastasis. Grade and/or stage if available.",
        placeholder="Example: Primary tumor, Grade 3",
        key="form_sample_type",
        )

    path_lab_info = st.text_area(
        "Diagnosis: Short description",
        placeholder="Example: Squamous cell carcinoma",
        height=160,
        key="form_path_lab_info",
    )

    icd_code_descriptions = st.text_area(
        "Other Classification Information: If available, descriptive text associated with ICD code(s).",
        placeholder="Example: Carcinoma, Squamous cell, NOS",
        height=120,
        key="form_icd_code_descriptions",
    )

    other_comments = st.text_area(
        "Comments (Optional): Long description, often with IHC results.",
        placeholder="Example: Invasive, poorly differentiated squamous cell carcinoma with cellular and nuclear atypia. p40 positive by IHC.",
        height=120,
        key="form_other_comments",
    )


    submit_form = st.button("Classify", key = "classify_form")
    submit_demo_form = st.session_state.pop("submit_demo_form", False)

    if submit_form or submit_demo_form:
        if not validate_model_selection():
            pass
        elif not form_cloud_confirmed:
            st.error("Please confirm there is no PHI present before using a cloud model.")
        elif not icd_code_descriptions.strip() and not path_lab_info.strip() and not other_comments.strip():
                st.error("Please enter at least a diagnosis, ICD code description, or other comments.")
        else:
            diagnosis_parts = []

            if path_lab_info.strip():
                diagnosis_parts.append(path_lab_info.strip())

            if other_comments.strip():
                diagnosis_parts.append(f"Other Comments: {other_comments.strip()}")

            if sample_type.strip():
                diagnosis_parts.append(f"Sample Type: {sample_type.strip()}")

            path_lab_info = "; ".join(diagnosis_parts)

            input_record = build_oncotree_input_json(
                icd_code_descriptions=icd_code_descriptions,
                path_lab_info=path_lab_info,
                test_order_id=test_order_id.strip() or f"case_{uuid.uuid4().hex[:8]}",
                sample_site=sample_site,
            )

            with st.spinner("Running OncoTree classifier..."):
                result = run_oncotree_classifier(
                    input_record=input_record,
                    selected_model=st.session_state.selected_model,
                    selected_model_source=st.session_state.selected_model_source,
                    api_key=st.session_state.ollama_cloud_api_key,
                )
                if result["returncode"] != 0:
                    logger.error(
                        "CLASSIFIER_ERROR session_id=%s input_mode=form returncode=%s",
                        st.session_state.get("session_id"),
                        result["returncode"],
                    )

            st.session_state.form_input_record = input_record
            st.session_state.form_classifier_result = result

    if st.session_state.form_classifier_result is not None:
        with st.expander("Input JSON sent to classifier", expanded=False):
            st.json(st.session_state.form_input_record)

        display_classifier_result(
            st.session_state.form_classifier_result,
            key_prefix="form",
            download_case_id=st.session_state.form_input_record.get("test_order_id"),
        )


with batch_tab:
    st.subheader("Batch classify uploaded files")
    st.caption("Batch mode autodetects JSON files by default and processes PDF, TXT, DOCX, and JSON uploads in sequence.")

    if IS_VM_ENVIRONMENT:
        st.info(f"Batch uploads are limited to {VM_BATCH_FILE_LIMIT} files.")

    batch_cloud_confirmed = cloud_uploads_allowed("batch_cloud_phi_confirm")
    batch_files = st.file_uploader(
        "Upload reports",
        type=["txt", "pdf", "docx", "json"],
        accept_multiple_files=True,
        key=upload_widget_key("batch_uploaded_files", batch_cloud_confirmed),
        disabled=upload_widget_disabled(batch_cloud_confirmed),
    )
    batch_json_input_type = JSON_INPUT_AUTO
    batch_pdf_page_limit = DEFAULT_PDF_PAGE_LIMIT

    if batch_files and any(file.name.lower().endswith(".json") for file in batch_files):
        batch_json_label = st.selectbox(
            "JSON handling for batch uploads",
            options=list(JSON_INPUT_TYPE_OPTIONS),
            help="Auto-detect checks each JSON file. Choose an explicit type when all JSON files use the same format.",
            key="batch_json_input_type_label",
        )
        batch_json_input_type = JSON_INPUT_TYPE_OPTIONS[batch_json_label]

    if batch_files and any(file.name.lower().endswith(".pdf") for file in batch_files):
        batch_pdf_page_limit = st.number_input(
            "PDF pages to process",
            min_value=1,
            value=DEFAULT_PDF_PAGE_LIMIT,
            step=1,
            help = "Applies to each PDF in the batch. Fewer pages usually means faster processing.",
            key="batch_pdf_page_limit",
        )

    if st.button("Run batch classification", key="classify_batch"):
        if not validate_model_selection():
            pass
        elif not batch_cloud_confirmed:
            st.error("Please confirm there is no PHI present before using a cloud model.")
        elif not batch_files:
            st.error("Please upload at least one file.")
        elif IS_VM_ENVIRONMENT and len(batch_files) > VM_BATCH_FILE_LIMIT:
            st.error(f"Batch uploads are limited to {VM_BATCH_FILE_LIMIT} files on the VM.")
        else:
            logger.info(
                "BATCH_MODE_INITIATED session_id=%s file_count=%s",
                st.session_state.get("session_id"),
                len(batch_files),
            )
            progress = st.progress(0)
            status_text = st.empty()
            batch_results = []

            for index, uploaded_file in enumerate(batch_files, start=1):
                status_text.write(f"Processing {uploaded_file.name} ({index} of {len(batch_files)})")

                try:
                    input_record = uploaded_file_to_oncotree_input(
                        uploaded_file,
                        json_input_type=batch_json_input_type,
                        pdf_page_limit=batch_pdf_page_limit,
                    )

                    result = run_oncotree_classifier(
                        input_record=input_record,
                        selected_model=st.session_state.selected_model,
                        selected_model_source=st.session_state.selected_model_source,
                        api_key=st.session_state.ollama_cloud_api_key,
                    )
                    if result["returncode"] != 0:
                        logger.error(
                            "CLASSIFIER_ERROR session_id=%s input_mode=batch batch_index=%s returncode=%s",
                            st.session_state.get("session_id"),
                            index,
                            result["returncode"],
                        )

                    batch_results.append(
                        {
                            "filename": uploaded_file.name,
                            "input_record": input_record,
                            "result": result,
                            "error": None,
                        }
                    )
                except Exception as e:
                    logger.error(
                        "BATCH_FILE_ERROR session_id=%s input_mode=batch batch_index=%s error_type=%s",
                        st.session_state.get("session_id"),
                        index,
                        type(e).__name__,
                    )
                    batch_results.append(
                        {
                            "filename": uploaded_file.name,
                            "input_record": None,
                            "result": None,
                            "error": str(e),
                        }
                    )

                progress.progress(index / len(batch_files))

            status_text.write("Batch classification complete.")
            st.session_state.batch_results = batch_results

    if st.session_state.batch_results:
        successful_results = [
            item
            for item in st.session_state.batch_results
            if item["input_record"] and item["result"] and not item["error"]
        ]
        failed_results = [
            item
            for item in st.session_state.batch_results
            if item["error"]
        ]

        total_col, success_col, failed_col = st.columns(3)
        total_col.metric("Files", len(st.session_state.batch_results))
        success_col.metric("Completed", len(successful_results))
        failed_col.metric("Failed", len(failed_results))

        if successful_results:
            st.download_button(
                "Download batch results ZIP",
                data=zip_batch_output_files(successful_results),
                file_name="oncotree_batch_results.zip",
                mime="application/zip",
                key="download_batch_results",
            )

        result_options = list(range(len(st.session_state.batch_results)))
        st.space("small")
        st.subheader("Select result to view")
        selected_index = st.selectbox(
            "Batch result:",
            result_options,
            key="selected_batch_result",
            label_visibility="collapsed",
            format_func=lambda index: (
                f"{'ERROR - ' if st.session_state.batch_results[index]['error'] else ''}"
                f"{st.session_state.batch_results[index]['filename']}"
            ),
        )
        item = st.session_state.batch_results[selected_index]

        if item["error"]:
            st.error(item["error"])
        else:
            with st.expander("Input JSON sent to classifier", expanded=False):
                st.json(item["input_record"])

            if st.checkbox("Show OncoTree", key=f"show_batch_oncotree_{selected_index}"):
                display_oncotree_tree(item["result"]["output_files"], key_prefix=f"batch_{selected_index}")

            display_classifier_result(
                item["result"],
                key_prefix=f"batch_{selected_index}",
                show_oncotree=False,
                show_download_zip=False,
                show_output_files=False,
            )
