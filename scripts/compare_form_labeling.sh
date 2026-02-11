#!/usr/bin/env bash
# Compare programmatic vs vision-based labeling for PDF forms
# Usage: bash scripts/compare_form_labeling.sh <form_url> <project_base_name>

set -euo pipefail

FORM_URL="${1:-}"
PROJECT_BASE="${2:-form-comparison}"

if [ -z "$FORM_URL" ]; then
  echo "Usage: bash scripts/compare_form_labeling.sh <form_url> <project_base_name>"
  echo "Example: bash scripts/compare_form_labeling.sh https://courts.ca.gov/.../ud101.pdf ud101"
  exit 1
fi

echo "=== Comparing Programmatic vs Vision Labeling ==="
echo "Form URL: $FORM_URL"
echo "Base project: $PROJECT_BASE"
echo ""

# Run 1: Programmatic labeling (fast, free)
echo "--- Run 1: Programmatic Labeling ---"
python3 - <<EOF
import json
config = json.load(open("config.json"))
config["project"] = "${PROJECT_BASE}-programmatic"
config["source_type"] = "form"
config["form_url"] = "${FORM_URL}"
config["form_label_mode"] = "programmatic"
config["num_variations"] = 50
config["target_accuracy"] = 0.75
json.dump(config, open("config.json", "w"), indent=2)
EOF

bash formdex.sh 5

# Save results
cp "runs/${PROJECT_BASE}-programmatic/eval_results.json" "runs/${PROJECT_BASE}-programmatic-results.json"

# Run 2: Vision labeling (agents)
echo ""
echo "--- Run 2: Vision Labeling (Codex agents) ---"
python3 - <<EOF
import json
config = json.load(open("config.json"))
config["project"] = "${PROJECT_BASE}-vision"
config["source_type"] = "form"
config["form_url"] = "${FORM_URL}"
config["form_label_mode"] = "vision"
config["label_mode"] = "codex"
config["num_variations"] = 50
config["num_agents"] = 4
config["target_accuracy"] = 0.75
json.dump(config, open("config.json", "w"), indent=2)
EOF

bash formdex.sh 5

# Save results
cp "runs/${PROJECT_BASE}-vision/eval_results.json" "runs/${PROJECT_BASE}-vision-results.json"

# Compare
echo ""
echo "=== Results Comparison ==="
python3 - <<EOF
import json

prog = json.load(open("runs/${PROJECT_BASE}-programmatic-results.json"))
vis = json.load(open("runs/${PROJECT_BASE}-vision-results.json"))

print("Programmatic Labeling:")
print(f"  mAP@50: {prog['map50']:.4f}")
print(f"  Precision: {prog['precision']:.4f}")
print(f"  Recall: {prog['recall']:.4f}")
print(f"  Meets target: {prog['meets_target']}")

print("")
print("Vision Labeling (Codex):")
print(f"  mAP@50: {vis['map50']:.4f}")
print(f"  Precision: {vis['precision']:.4f}")
print(f"  Recall: {vis['recall']:.4f}")
print(f"  Meets target: {vis['meets_target']}")

print("")
winner = "Programmatic" if prog['map50'] > vis['map50'] else "Vision"
diff = abs(prog['map50'] - vis['map50'])
print(f"Winner: {winner} (by {diff:.4f} mAP@50)")
EOF

echo ""
echo "Results saved:"
echo "  - runs/${PROJECT_BASE}-programmatic-results.json"
echo "  - runs/${PROJECT_BASE}-vision-results.json"

