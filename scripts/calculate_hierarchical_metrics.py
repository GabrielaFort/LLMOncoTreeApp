#!/usr/bin/env python3
"""Calculate OncoTree hierarchical precision, recall, and F1 from JSON files.

Correct-answer JSON:
{
  "sample_1": "IDC",
  "sample_2": ["MAAP", "APAD"]
}

Prediction JSON:
{
  "sample_1": "DCIS",
  "sample_2": "MAAP"
}

For multiple acceptable truths, the candidate with the highest hierarchical
F1 is used. The universal OncoTree root is excluded from all paths.

Also requires a nested OncoTree JSON file, from the OncoTree API.
E.g. from "https://oncotree.mskcc.org/api/tumorTypes/tree?version=oncotree_latest_stable"

Output JSON:
{
  "summary": {
    "n_samples": number of evaluated samples,
    "exact_accuracy": fraction with exact truth/prediction code match,
    "hP": corpus-level hierarchical precision,
    "hR": corpus-level hierarchical recall,
    "hF1": corpus-level hierarchical F1,
    "unknown_predictions": count of predicted codes not found in OncoTree
  },
  "samples": {
    "sample_1": {
      "truth_used": acceptable truth code that gave the best hF1,
      "prediction": normalized predicted code,
      "exact": true when truth_used equals prediction,
      "hP": sample-level hierarchical precision,
      "hR": sample-level hierarchical recall,
      "hF1": sample-level hierarchical F1,
      "shared_labels": number of overlapping OncoTree path labels,
      "predicted_labels": number of labels in the predicted path,
      "true_labels": number of labels in the truth path,
      "prediction_known": true when prediction exists in OncoTree,
      "acceptable_truths": normalized list of acceptable truth codes
    }
  }
}
"""

import argparse
import json
from pathlib import Path


def load_tree(path):
    """Load nested OncoTree JSON and return root code plus parent links."""
    data = json.loads(Path(path).read_text())
    root_node = next(iter(data.values()))
    root_code = root_node["code"].upper()
    parents = {}

    def walk(node):
        """Recursively flatten each node into a code -> parent-code mapping."""
        code = node["code"].strip().upper()
        parent = node.get("parent")
        parents[code] = parent.strip().upper() if parent else None

        children = node.get("children") or {}
        for child in children.values() if isinstance(children, dict) else children:
            walk(child)

    walk(root_node)
    return root_code, parents


def normalize(code):
    """Standardize OncoTree codes before lookup or comparison."""
    if code is None:
        return None
    return str(code).strip().upper()


def ancestor_path(code, root, parents):
    """Return the node and its ancestors, excluding the universal root."""
    code = normalize(code)
    if not code:
        return set()
    if code not in parents:
        # Unknown predictions remain singleton labels, giving zero overlap.
        return {code}

    path = set()
    while code and code != root:
        if code in path:
            raise ValueError(f"Cycle in OncoTree at {code}")
        path.add(code)
        code = parents.get(code)
    return path


def score_pair(truth, prediction, root, parents):
    """Score one truth/prediction pair using overlap of ancestor paths."""
    truth = normalize(truth)
    prediction = normalize(prediction)

    if truth not in parents:
        raise ValueError(f"Truth code is not in OncoTree: {truth}")

    true_path = ancestor_path(truth, root, parents)
    predicted_path = ancestor_path(prediction, root, parents)
    shared = true_path & predicted_path

    # Hierarchical precision asks how much of the predicted path is correct;
    # Hierarchical recall asks how much of the truth path was recovered.
    hp = len(shared) / len(predicted_path) if predicted_path else 0.0
    hr = len(shared) / len(true_path) if true_path else 0.0
    hf1 = 2 * hp * hr / (hp + hr) if hp + hr else 0.0

    return {
        "truth_used": truth,
        "prediction": prediction,
        "exact": truth == prediction,
        "hP": hp,
        "hR": hr,
        "hF1": hf1,
        "shared_labels": len(shared),
        "predicted_labels": len(predicted_path),
        "true_labels": len(true_path),
        "prediction_known": prediction in parents,
    }


def calculate_metrics(tree_json, correct_json, prediction_json):
    """Calculate per-sample scores and summary micro-average metrics."""
    root, parents = load_tree(tree_json)
    correct = json.loads(Path(correct_json).read_text())
    predictions = json.loads(Path(prediction_json).read_text())

    # Require identical sample IDs 
    missing = sorted(set(correct) - set(predictions))
    extra = sorted(set(predictions) - set(correct))
    if missing or extra:
        raise ValueError(
            f"Sample-name mismatch. Missing predictions: {missing}; "
            f"unexpected predictions: {extra}"
        )

    per_sample = {}
    for sample, acceptable_truths in correct.items():
        if not isinstance(acceptable_truths, list):
            acceptable_truths = [acceptable_truths]
        if not acceptable_truths:
            raise ValueError(f"No correct answer supplied for {sample}")

        # Some cases have multiple acceptable labels. Score each option against
        # the same prediction and keep the best one for this sample.
        candidates = [
            score_pair(truth, predictions[sample], root, parents)
            for truth in acceptable_truths
        ]
        # Treat alternatives as acceptable answers.
        best = max(
            candidates,
            key=lambda score: (
                score["hF1"], score["exact"],
                score["shared_labels"], score["hR"],
            ),
        )
        best["acceptable_truths"] = [normalize(x) for x in acceptable_truths]
        per_sample[sample] = best

    # Micro-average across all path labels, rather than averaging per-sample
    # precision/recall. This gives each path label equal weight.
    shared = sum(x["shared_labels"] for x in per_sample.values())
    predicted = sum(x["predicted_labels"] for x in per_sample.values())
    true = sum(x["true_labels"] for x in per_sample.values())
    hp = shared / predicted if predicted else 0.0
    hr = shared / true if true else 0.0
    hf1 = 2 * hp * hr / (hp + hr) if hp + hr else 0.0

    return {
        "summary": {
            "n_samples": len(per_sample),
            "exact_accuracy": sum(x["exact"] for x in per_sample.values()) / len(per_sample),
            "hP": hp,
            "hR": hr,
            "hF1": hf1,
            "unknown_predictions": sum(not x["prediction_known"] for x in per_sample.values()),
        },
        "samples": per_sample,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tree", required=True, help="Nested OncoTree JSON")
    parser.add_argument("--correct", required=True, help="Sample-to-correct-answer JSON")
    parser.add_argument("--predictions", required=True, help="Sample-to-prediction JSON")
    parser.add_argument("--output", help="Optional output JSON; otherwise print to stdout")
    args = parser.parse_args()

    results = calculate_metrics(args.tree, args.correct, args.predictions)
    text = json.dumps(results, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n")
    else:
        print(text)


if __name__ == "__main__":
    main()
