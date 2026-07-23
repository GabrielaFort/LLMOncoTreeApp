import argparse
from pathlib import Path

from oncotree_runner import (
    file_path_to_oncotree_input,
    get_model_source,
    run_oncotree_classifier,
)


def iter_input_files(input_path):
    input_path = Path(input_path)
    allowed_suffixes = {".json", ".txt", ".docx", ".pdf"}

    if input_path.is_file():
        if input_path.suffix.lower() in allowed_suffixes:
            yield input_path
        return

    for path in sorted(input_path.iterdir()):
        if path.is_file() and path.suffix.lower() in allowed_suffixes:
            yield path


def main():
    parser = argparse.ArgumentParser(description="Batch classify reports with the OncoTree classifier.")
    parser.add_argument("--input", required=True, help="Input file or directory of reports.")
    parser.add_argument("--model", required=True, help="Ollama model name.")
    parser.add_argument("--api-key-file", help="File containing Ollama Cloud API key.")
    parser.add_argument(
        "--ollama-host",
        help="Local Ollama host URL, e.g. http://127.0.0.1:11434. Ignored for cloud models.",
    )
    args = parser.parse_args()
    model_source = get_model_source(args.model)

    api_key = None
    if args.api_key_file:
        api_key = Path(args.api_key_file).read_text(encoding="utf-8").strip()
    if model_source == "cloud" and not api_key:
        raise SystemExit("Cloud models require --api-key-file.")

    files = list(iter_input_files(args.input))
    if not files:
        raise SystemExit("No supported input files found.")

    for path in files:
        print(f"Processing {path.name}")
        input_record = file_path_to_oncotree_input(
            path,
            args.model,
            api_key=api_key,
            ollama_host=args.ollama_host,
        )
        result = run_oncotree_classifier(
            input_record=input_record,
            selected_model=args.model,
            api_key=api_key,
            ollama_host=args.ollama_host,
        )

        if result["returncode"] == 0:
            print(f"  done: {input_record.get('test_order_id')}")
        else:
            print(f"  failed: {result['stderr']}")


if __name__ == "__main__":
    main()
