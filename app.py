import streamlit as st
import ollama
import requests
import base64
import os
from pathlib import Path
import html
import json
import uuid
from urllib.parse import urlencode
from report_input_parser import (
    build_oncotree_input_json,
    convert_pdf_bytes_to_md,
    extract_docx_text,
    get_model_source,
)
from oncotree_runner import (
    APP_DIR,
    run_oncotree_classifier,
    uploaded_file_to_oncotree_input as runner_uploaded_file_to_oncotree_input,
    zip_batch_output_files,
    zip_output_files,
)

ONCOTREE_BASE_URL = "https://oncotree.mskcc.org/"
FULL_ONCOTREE_JSON_PATH = APP_DIR / "full_oncotree.json"
CLOUD_PHI_WARNING = "Warning: You are about to submit your file(s) to a cloud hosted AI model. Please ensure there is no PHI present before submission"
RUN_ENVIRONMENT = os.environ.get("RUN_ENVIRONMENT", "LOCAL").strip().upper()
IS_VM_ENVIRONMENT = RUN_ENVIRONMENT == "VM"
try:
    VM_BATCH_FILE_LIMIT = int(os.environ.get("VM_BATCH_FILE_LIMIT", "10"))
except ValueError:
    VM_BATCH_FILE_LIMIT = 10

DEMO_FORM_INPUT = {
    "test_order_id": "12345",
    "sample_site": "Lung, lower lobe",
    "sample_type": "Primary tumor, Grade 3",
    "path_lab_info": "Squamous cell carcinoma",
    "icd_code_descriptions": "Carcinoma, Squamous Cell, NOS",
    "other_comments": "Invasive, poorly differentiated squamous cell carcinoma with cellular and nuclear atypia. p40 positive by IHC.",
}

# Add custom CSS for styled tabs
st.markdown("""
<style>
    /* Style the tab buttons */
    .stTabs [data-baseweb="tab-list"] {
        gap: 12px;
        background-color: transparent;
        padding: 8px 0;
    }

    .stTabs [data-baseweb="tab"] {
        height: 50px;
        background-color: #f0f2f6;
        border-radius: 12px 12px 0 0;
        padding: 10px 20px;
        font-weight: 600;
        border: 2px solid #e0e0e0;
        border-bottom: none;
        transition: all 0.3s ease;
    }

    .stTabs [data-baseweb="tab"]:hover {
        background-color: #e8eaf0;
        transform: translateY(-2px);
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
    }

    .stTabs [aria-selected="true"] {
        background-color: #ffffff !important;
        border-color: #6c757d !important;
        border-bottom: 2px solid #ffffff !important;
        box-shadow: 0 -2px 8px rgba(108, 117, 125, 0.2);
    }

</style>
""", unsafe_allow_html=True)

st.set_page_config(page_title = "LLM OncoTree Classifier", layout = "centered", initial_sidebar_state = "expanded")
st.title("LLM OncoTree Classifier")
st.text("This app utilizes an LLM to classify cancer types from uploaded test results or pathology reports using the OncoTree ontology.")


# Function to auto-detect local LLMs on machine, assuming Ollama is running
def discover_local_ollama_models():
    """
    Return a sorted list of model names from ollama.list()
    """
    try:
        models = ollama.list()["models"]
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
    st.iframe(oncotree_url, height=800)


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


# LLM settings sidebar
st.sidebar.header("LLM Settings")
available_local_models = discover_local_ollama_models()

# Show sidebar message if no local models are found
if not available_local_models:
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
            cloud_models = discover_ollama_cloud_models()
            cloud_models = [
                model if model.endswith("-cloud") else f"{model}-cloud" for model in cloud_models
            ]
            st.session_state.available_cloud_models = cloud_models
            if cloud_models:
                st.success(f"Loaded {len(cloud_models)} cloud models.")
            else:
                st.warning("No cloud models found.")

    # Build one list of available models; cloud/local is inferred from the model name.
    model_options = ["No model selected"] + sorted(
        set(available_local_models + st.session_state.available_cloud_models)
    )

selected_model_label = st.sidebar.selectbox("Select Model", options=model_options, index=0, key ="selected_model_label")

selected_model = None
selected_model_source = None

if st.session_state.selected_model_label != "No model selected":
    selected_model = st.session_state.selected_model_label
    selected_model_source = get_model_source(selected_model)

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

def get_uploaded_pdf_md(uploaded_file):
    if (
        st.session_state.get("uploaded_pdf_md_name") != uploaded_file.name
        or "uploaded_pdf_md" not in st.session_state
    ):
        st.session_state.uploaded_pdf_md_name = uploaded_file.name
        st.session_state.uploaded_pdf_md = convert_pdf_bytes_to_md(uploaded_file.getvalue())

    return st.session_state.uploaded_pdf_md


def uploaded_file_to_oncotree_input(uploaded_file):
    return runner_uploaded_file_to_oncotree_input(
        uploaded_file,
        st.session_state.selected_model,
        st.session_state.selected_model_source,
        st.session_state.ollama_cloud_api_key,
        pdf_text_getter=get_uploaded_pdf_md,
    )


# File upload tab
with file_tab:
    st.subheader("Classify from uploaded file")

    uploaded_file = st.file_uploader("Upload pathology report or test result",
                                     type = ["txt", "pdf", "docx", "json"],
                                     key = "uploaded_report_file")
    if uploaded_file is not None:
        uploaded_bytes = uploaded_file.getvalue()
        pdf_md = None

        st.success(f"Loaded file: {uploaded_file.name}")

        if uploaded_file.name.lower().endswith(".pdf"):
            with st.spinner("Converting PDF to text..."):
                try:
                    pdf_md = get_uploaded_pdf_md(uploaded_file)
                except Exception as e:
                    st.error(f"Error converting PDF to text: {e}")

        with st.expander("Preview uploaded file", expanded=False):
            if uploaded_file.name.lower().endswith(".pdf"):
                render_pdf(uploaded_bytes, height=800)
                st.text_area(
                    "Text preview",
                    value=pdf_md if pdf_md else "No readable text extracted from the PDF.",
                    height=400,
                    disabled=True,
                    key="uploaded_pdf_md_preview",
                )

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
                    st.error(f"Error loading DOCX file: {e}")
            
            elif uploaded_file.name.lower().endswith(".json"):
                try:
                    preview_json = json.loads(uploaded_bytes.decode("utf-8"))
                    st.json(preview_json)
                except Exception as e:
                    st.error(f"Error loading JSON file: {e}")
                
        
    file_cloud_confirmed = confirm_cloud_submission("file_cloud_phi_confirm")

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
                    input_record = uploaded_file_to_oncotree_input(uploaded_file)

            except Exception as e:
                st.error(f"Error processing uploaded file: {e}")

        if input_record is not None:
            with st.spinner("Running OncoTree classifier..."):
                result = run_oncotree_classifier(
                    input_record=input_record,
                    selected_model=st.session_state.selected_model,
                    selected_model_source=st.session_state.selected_model_source,
                    api_key=st.session_state.ollama_cloud_api_key,
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

    if IS_VM_ENVIRONMENT:
        st.info(f"Batch uploads are limited to {VM_BATCH_FILE_LIMIT} files.")

    batch_files = st.file_uploader(
        "Upload reports",
        type=["txt", "pdf", "docx", "json"],
        accept_multiple_files=True,
        key="batch_uploaded_files",
    )

    batch_cloud_confirmed = confirm_cloud_submission("batch_cloud_phi_confirm")

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
            progress = st.progress(0)
            status_text = st.empty()
            batch_results = []

            for index, uploaded_file in enumerate(batch_files, start=1):
                status_text.write(f"Processing {uploaded_file.name} ({index} of {len(batch_files)})")

                try:
                    input_record = uploaded_file_to_oncotree_input(uploaded_file)

                    result = run_oncotree_classifier(
                        input_record=input_record,
                        selected_model=st.session_state.selected_model,
                        selected_model_source=st.session_state.selected_model_source,
                        api_key=st.session_state.ollama_cloud_api_key,
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

        if successful_results:
            st.download_button(
                "Download batch results ZIP",
                data=zip_batch_output_files(successful_results),
                file_name="oncotree_batch_results.zip",
                mime="application/zip",
                key="download_batch_results",
            )

        result_options = list(range(len(st.session_state.batch_results)))
        selected_index = st.selectbox(
            "**Select result to view**",
            result_options,
            key="selected_batch_result",
            format_func=lambda index: (
                f"{'ERROR - ' if st.session_state.batch_results[index]['error'] else ''}"
                f"{st.session_state.batch_results[index]['filename']}"
            ),
        )
        item = st.session_state.batch_results[selected_index]

        st.markdown(f"### {item['filename']}")

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
