#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# train_paperspace_with_vision.sh — Label locally with agents, train on GPU
#
# This workflow uses Codex agents for vision-based labeling on your Mac,
# then uploads the labeled data to Paperspace for fast GPU training.
#
# Usage:
#   bash scripts/train_paperspace_with_vision.sh paperspace@<your-ip>
#
# What this does:
#   1. Run collect_form locally (render images)
#   2. Run Codex agents locally (label images)
#   3. Run augment locally (augment data)
#   4. Upload labeled data to Paperspace via rsync
#   5. SSH to Paperspace and run training
#   6. Download trained model back to your Mac
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

PAPERSPACE_HOST="${1:-}"

if [ -z "$PAPERSPACE_HOST" ]; then
  echo "Usage: bash scripts/train_paperspace_with_vision.sh paperspace@<your-ip>"
  echo ""
  echo "Example:"
  echo "  bash scripts/train_paperspace_with_vision.sh paperspace@184.105.6.123"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

# Load config
PROJECT=$(python3 -c "import json; print(json.load(open('config.json')).get('project', 'output'))" 2>/dev/null || echo "output")
FORM_LABEL_MODE=$(python3 -c "import json; print(json.load(open('config.json')).get('form_label_mode', 'programmatic'))" 2>/dev/null || echo "programmatic")

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  FormDex — Hybrid Workflow (Label Local, Train Remote)  ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "Project: $PROJECT"
echo "Paperspace: $PAPERSPACE_HOST"
echo "Label mode: $FORM_LABEL_MODE"
echo ""

# Verify config is set to vision mode
if [ "$FORM_LABEL_MODE" != "vision" ]; then
  echo "⚠️  WARNING: form_label_mode is set to '$FORM_LABEL_MODE'"
  echo ""
  echo "This script is designed for vision-based labeling with agents."
  echo "Your config should have:"
  echo "  \"form_label_mode\": \"vision\""
  echo "  \"label_mode\": \"codex\"  (or gemini/gpt/cua+sam)"
  echo ""
  read -p "Continue anyway? (y/N): " cont
  if [[ ! "$cont" =~ ^[Yy] ]]; then
    exit 1
  fi
fi

# ── Step 1: Collect (local) ───────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 1/6: Collect form data (local)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

FRAMES_DIR="runs/$PROJECT/frames"
if [ -d "$FRAMES_DIR" ] && [ "$(ls -A "$FRAMES_DIR" 2>/dev/null | head -1)" ]; then
  FRAME_COUNT=$(ls "$FRAMES_DIR"/*.jpg 2>/dev/null | wc -l || echo 0)
  echo "✅ Frames already exist ($FRAME_COUNT images) — skipping"
else
  echo "Rendering PDF forms..."
  uv run .agents/skills/collect/scripts/collect_form.py
fi
echo ""

# ── Step 2: Label (local with agents) ─────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 2/6: Label images with agents (local)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Check if labels already exist
LABEL_COUNT=$(ls "$FRAMES_DIR"/*.txt 2>/dev/null | wc -l || echo 0)
if [ "$LABEL_COUNT" -gt 0 ]; then
  echo "✅ Labels already exist ($LABEL_COUNT files) — skipping"
else
  echo "Labeling with Codex agents..."
  LABEL_MODE=$(python3 -c "import json; print(json.load(open('config.json')).get('label_mode', 'codex'))")
  NUM_AGENTS=$(python3 -c "import json; print(json.load(open('config.json')).get('num_agents', 4))")
  
  if [ "$LABEL_MODE" = "codex" ] || [ "$LABEL_MODE" = "gpt" ]; then
    # Use parallel dispatch
    bash .agents/skills/label/scripts/dispatch.sh "$NUM_AGENTS"
  elif [ "$LABEL_MODE" = "cua+sam" ]; then
    uv run .agents/skills/label/scripts/label_cua_sam.py
  elif [ "$LABEL_MODE" = "gemini" ]; then
    uv run .agents/skills/label/scripts/label_gemini.py
  else
    uv run .agents/skills/label/scripts/run.py
  fi
fi
echo ""

# ── Step 3: Augment (local) ───────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 3/6: Augment data (local)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

AUG_DIR="runs/$PROJECT/augmented"
if [ -d "$AUG_DIR" ] && [ "$(ls -A "$AUG_DIR" 2>/dev/null | head -1)" ]; then
  AUG_COUNT=$(ls "$AUG_DIR"/*.jpg 2>/dev/null | wc -l || echo 0)
  echo "✅ Augmented data already exists ($AUG_COUNT images) — skipping"
else
  echo "Running augmentation..."
  uv run .agents/skills/augment/scripts/run.py
fi
echo ""

# ── Step 4: Upload to Paperspace ──────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 4/6: Upload data to Paperspace"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Uploading config.json + runs/$PROJECT/ to $PAPERSPACE_HOST..."
echo ""

# Upload config
rsync -avz --progress config.json "$PAPERSPACE_HOST:~/formdex/"

# Upload project data
rsync -avz --progress \
  --include='*.jpg' \
  --include='*.txt' \
  --include='*.json' \
  --exclude='*.pt' \
  --exclude='yolo_run/' \
  "runs/$PROJECT/" \
  "$PAPERSPACE_HOST:~/formdex/runs/$PROJECT/"

echo ""
echo "✅ Upload complete"
echo ""

# ── Step 5: Train on Paperspace ───────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 5/6: Train model on Paperspace GPU"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Running training on remote GPU..."
echo ""

# Create a remote training script that skips collect/label/augment
ssh "$PAPERSPACE_HOST" bash << 'EOF'
cd ~/formdex
echo "[remote] Starting GPU training..."

# Install uv if needed
if ! command -v uv &> /dev/null; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# Sync deps
uv sync --quiet

# Get project name
PROJECT=$(uv run python -c "import json; print(json.load(open('config.json')).get('project', 'output'))")

# Run train + eval (skip collect/label/augment since we uploaded labeled data)
echo "[remote] Training..."
uv run .agents/skills/train/scripts/run.py

echo "[remote] Evaluating..."
uv run .agents/skills/eval/scripts/run.py

# Show results
if [ -f "runs/$PROJECT/eval_results.json" ]; then
  echo ""
  echo "╔══════════════════════════════════════════════════════════╗"
  echo "║  Training Complete!                                      ║"
  echo "╚══════════════════════════════════════════════════════════╝"
  echo ""
  uv run python -c "
import json
r = json.load(open('runs/$PROJECT/eval_results.json'))
print(f'  mAP@50:     {r[\"map50\"]:.4f}')
print(f'  mAP@50-95:  {r[\"map50_95\"]:.4f}')
print(f'  Precision:  {r[\"precision\"]:.4f}')
print(f'  Recall:     {r[\"recall\"]:.4f}')
print(f'  Meets target: {\"✅ YES\" if r[\"meets_target\"] else \"❌ NO\"}')
"
else
  echo "❌ Training failed — eval_results.json not found"
  exit 1
fi
EOF

echo ""
echo "✅ Training complete"
echo ""

# ── Step 6: Download results ──────────────────────────────────────────────
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "STEP 6/6: Download trained model"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

echo "Downloading best.pt and eval_results.json..."
mkdir -p "runs/$PROJECT/weights"
scp "$PAPERSPACE_HOST:~/formdex/runs/$PROJECT/weights/best.pt" "runs/$PROJECT/weights/"
scp "$PAPERSPACE_HOST:~/formdex/runs/$PROJECT/eval_results.json" "runs/$PROJECT/"

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║  ✅ COMPLETE — Model trained on Paperspace GPU           ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
echo "  Model weights: runs/$PROJECT/weights/best.pt"
echo "  Eval results:  runs/$PROJECT/eval_results.json"
echo ""
echo "  To use the model:"
echo "    from ultralytics import YOLO"
echo "    model = YOLO('runs/$PROJECT/weights/best.pt')"
echo "    results = model.predict('your_form.pdf')"
echo ""

