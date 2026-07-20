import argparse
import csv
import json
import re
from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile


DEFAULT_TRUTH_XLSX = Path("tcga_benchmark_100/TCGA_download_100_cases.xlsx")
DEFAULT_PDF_RESULTS = Path("tcga_benchmark_100/pdf_results_gemmae4b_local")
DEFAULT_TXT_RESULTS = Path("tcga_benchmark_100/txt_results_gemmae4b_local")
DEFAULT_ONCOTREE_JSON = Path("full_oncotree.json")
TCGA_PATIENT_RE = re.compile(r"TCGA-[A-Z0-9]{2}-[A-Z0-9]{4}", re.IGNORECASE)
XLSX_NS = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
TISSUE_CODE_ALIASES = {
    "GBM": "GB",
    "OAST": "ASTR",
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Evaluate TCGA OncoTree classifier outputs against TCGA benchmark truth codes."
    )
    parser.add_argument("--truth", type=Path, default=DEFAULT_TRUTH_XLSX)
    parser.add_argument("--pdf-results", type=Path, default=DEFAULT_PDF_RESULTS)
    parser.add_argument("--txt-results", type=Path, default=DEFAULT_TXT_RESULTS)
    parser.add_argument("--oncotree-json", type=Path, default=DEFAULT_ONCOTREE_JSON)
    parser.add_argument("--details-csv", type=Path, help="Optional CSV of per-case predictions.")
    return parser.parse_args()


def read_xlsx_rows(path):
    with ZipFile(path) as xlsx:
        shared_strings = []
        shared_root = ET.fromstring(xlsx.read("xl/sharedStrings.xml"))
        for item in shared_root.findall("a:si", XLSX_NS):
            text_parts = [text.text or "" for text in item.findall(".//a:t", XLSX_NS)]
            shared_strings.append("".join(text_parts))

        sheet_root = ET.fromstring(xlsx.read("xl/worksheets/sheet1.xml"))
        rows = []
        for row in sheet_root.findall(".//a:row", XLSX_NS):
            values = []
            for cell in row.findall("a:c", XLSX_NS):
                value = cell.find("a:v", XLSX_NS)
                value = "" if value is None else value.text or ""
                if cell.attrib.get("t") == "s" and value:
                    value = shared_strings[int(value)]
                values.append(value)
            rows.append(values)

    header = rows[0]
    return [dict(zip(header, row)) for row in rows[1:]]


def normalize_code(value):
    value = "" if value is None else str(value)
    value = value.strip()
    return "" if value.upper() == "NA" else value.upper()


def load_truth_codes(path):
    truth = {}
    for row in read_xlsx_rows(path):
        patient_id = row.get("Patient ID")
        truth_code = normalize_code(row.get("Oncotree Code"))
        if patient_id and truth_code:
            truth[patient_id.upper()] = truth_code
    return truth


def load_tissue_code_map(path):
    nodes = json.loads(path.read_text(encoding="utf-8"))
    tissue_name_to_code = {
        node["tissue"]: node["code"]
        for node in nodes
        if node.get("level") == 1 and node.get("code") and node.get("tissue")
    }

    code_to_tissue_code = {}
    for node in nodes:
        code = node.get("code")
        tissue = node.get("tissue")
        tissue_code = tissue_name_to_code.get(tissue)
        if code and tissue_code:
            code_to_tissue_code[code.upper()] = tissue_code.upper()

    for old_code, current_code in TISSUE_CODE_ALIASES.items():
        if current_code in code_to_tissue_code:
            code_to_tissue_code[old_code] = code_to_tissue_code[current_code]

    return code_to_tissue_code


def patient_id_from_name(name):
    match = TCGA_PATIENT_RE.search(name)
    return match.group(0).upper() if match else None


def read_prediction_json(case_dir, folder_name):
    files = sorted((case_dir / folder_name).glob("*.json"))
    if not files:
        return {}

    with files[0].open(encoding="utf-8") as file:
        return json.load(file)


def read_predicted_code(case_dir):
    data = read_prediction_json(case_dir, "NodeClassified")
    return normalize_code(data.get("oncotree_code"))


def read_predicted_tissue_code(case_dir):
    data = read_prediction_json(case_dir, "TissueClassified")
    return normalize_code(data.get("oncotree_tissue_code"))


def summarize(rows, truth_field, prediction_field, correct_field):
    scored_rows = [row for row in rows if row[truth_field] and row[prediction_field]]
    correct_count = sum(1 for row in scored_rows if row[correct_field])
    accuracy = correct_count / len(scored_rows) if scored_rows else 0.0
    return correct_count, len(scored_rows), accuracy


def evaluate_result_dir(label, result_dir, truth_codes, tissue_code_map):
    rows = []

    for case_dir in sorted(path for path in result_dir.iterdir() if path.is_dir()):
        patient_id = patient_id_from_name(case_dir.name)
        truth_code = truth_codes.get(patient_id)
        truth_tissue_code = tissue_code_map.get(truth_code, "") if truth_code else ""
        predicted_code = read_predicted_code(case_dir)
        predicted_tissue_code = read_predicted_tissue_code(case_dir)
        node_correct = bool(truth_code and predicted_code and truth_code == predicted_code)
        tissue_correct = bool(
            truth_tissue_code
            and predicted_tissue_code
            and truth_tissue_code == predicted_tissue_code
        )

        rows.append(
            {
                "result_set": label,
                "case_dir": case_dir.name,
                "patient_id": patient_id or "",
                "truth_code": truth_code or "",
                "predicted_code": predicted_code or "",
                "node_correct": node_correct,
                "truth_tissue_code": truth_tissue_code,
                "predicted_tissue_code": predicted_tissue_code or "",
                "tissue_correct": tissue_correct,
            }
        )

    node_summary = summarize(rows, "truth_code", "predicted_code", "node_correct")
    tissue_summary = summarize(rows, "truth_tissue_code", "predicted_tissue_code", "tissue_correct")
    return rows, node_summary, tissue_summary


def print_summary(label, metric, summary):
    correct_count, total_count, accuracy = summary
    print(f"{label} {metric}: {correct_count}/{total_count} correct ({accuracy:.1%})")


def write_details_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "result_set",
        "case_dir",
        "patient_id",
        "truth_code",
        "predicted_code",
        "node_correct",
        "truth_tissue_code",
        "predicted_tissue_code",
        "tissue_correct",
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main():
    args = parse_args()
    truth_codes = load_truth_codes(args.truth)
    tissue_code_map = load_tissue_code_map(args.oncotree_json)

    pdf_rows, pdf_node_summary, pdf_tissue_summary = evaluate_result_dir(
        "pdf",
        args.pdf_results,
        truth_codes,
        tissue_code_map,
    )
    txt_rows, txt_node_summary, txt_tissue_summary = evaluate_result_dir(
        "txt",
        args.txt_results,
        truth_codes,
        tissue_code_map,
    )

    print_summary("PDF", "node", pdf_node_summary)
    print_summary("PDF", "tissue", pdf_tissue_summary)
    print_summary("TXT", "node", txt_node_summary)
    print_summary("TXT", "tissue", txt_tissue_summary)

    if args.details_csv:
        write_details_csv(args.details_csv, pdf_rows + txt_rows)
        print(f"Wrote details to {args.details_csv}")


if __name__ == "__main__":
    main()
