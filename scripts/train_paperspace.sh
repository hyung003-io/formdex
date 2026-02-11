#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────
# train_paperspace.sh — Run the full FormDex pipeline on Paperspace GPU
#
# Usage (from your local terminal):
#   1. SSH into your Paperspace machine:
#        ssh paperspace@<your-ip>
#   2. Clone the repo (or rsync your local copy):
#        git clone https://github.com/hyung003-io/formdex.git
#        cd formdex
#   3. Run this script:
#        bash scripts/train_paperspace.sh
#
# Or run it in one shot via SSH from your Mac:
#   ssh paperspace@<your-ip> 'cd formdex && bash scripts/train_paperspace.sh'
#
# What this does:
#   • Installs uv + Python dependencies
#   • Runs collect_form → augment → train → eval
#   • Uses CUDA GPU automatically (no MPS crashes)
#   • Copies best.pt to runs/<project>/weights/
# ─────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

echo "╔══════════════════════════════════════════════════════════╗"
echo "║  FormDex — Paperspace GPU Training Pipeline              ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# ── Step 0: Install dependencies ──────────────────────────────────────────
echo "[setup] Checking dependencies..."

# Install uv if missing
if ! command -v uv &> /dev/null; then
    echo "[setup] Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# Create venv and install Python deps
echo "[setup] Syncing Python dependencies..."
uv sync --quiet

# Verify CUDA is available
echo "[setup] Checking GPU..."
uv run python -c "
import torch
if torch.cuda.is_available():
    gpu = torch.cuda.get_device_name(0)
    mem = torch.cuda.get_device_properties(0).total_mem / 1e9
    print(f'[setup] ✅ CUDA GPU: {gpu} ({mem:.1f} GB)')
else:
    print('[setup] ⚠️  No CUDA GPU detected — training will use CPU (slow)')
"

# Read project name from config
PROJECT=$(uv run python -c "
import json
c = json.load(open('config.json'))
print(c.get('project', 'output'))
")
echo "[setup] Project: $PROJECT"
echo ""

# ── Step 1: Collect form (download PDF + synthetic data + auto-labels) ────
FRAMES_DIR="runs/$PROJECT/frames"
if [ -d "$FRAMES_DIR" ] && [ "$(ls -A "$FRAMES_DIR" 2>/dev/null | head -1)" ]; then
    FRAME_COUNT=$(ls "$FRAMES_DIR"/*.jpg 2>/dev/null | wc -l)
    echo "[collect] ✅ Frames already exist ($FRAME_COUNT images) — skipping"
else
    echo "[collect] Generating synthetic training data..."
    uv run .agents/skills/collect/scripts/collect_form.py
fi
echo ""

# ── Step 2: Augment ───────────────────────────────────────────────────────
AUG_DIR="runs/$PROJECT/augmented"
if [ -d "$AUG_DIR" ] && [ "$(ls -A "$AUG_DIR" 2>/dev/null | head -1)" ]; then
    AUG_COUNT=$(ls "$AUG_DIR"/*.jpg 2>/dev/null | wc -l)
    echo "[augment] ✅ Augmented data already exists ($AUG_COUNT images) — skipping"
else
    echo "[augment] Running augmentation (watermark, scan/fax, flip, noise)..."
    uv run .agents/skills/augment/scripts/run.py
fi
echo ""

# ── Step 3: Train ─────────────────────────────────────────────────────────
WEIGHTS="runs/$PROJECT/weights/best.pt"
echo "[train] Starting YOLOv8 training on GPU..."
echo "[train] This will take a few minutes with CUDA..."
uv run .agents/skills/train/scripts/run.py
echo ""

# ── Step 4: Eval ──────────────────────────────────────────────────────────
echo "[eval] Evaluating trained model..."
uv run .agents/skills/eval/scripts/run.py
echo ""

# ── Done ──────────────────────────────────────────────────────────────────
EVAL_FILE="runs/$PROJECT/eval_results.json"
if [ -f "$EVAL_FILE" ]; then
    echo "╔══════════════════════════════════════════════════════════╗"
    echo "║  Training Complete!                                      ║"
    echo "╚══════════════════════════════════════════════════════════╝"
    echo ""
    uv run python -c "
import json
r = json.load(open('$EVAL_FILE'))
print(f'  mAP@50:     {r[\"map50\"]:.4f}')
print(f'  mAP@50-95:  {r[\"map50_95\"]:.4f}')
print(f'  Precision:  {r[\"precision\"]:.4f}')
print(f'  Recall:     {r[\"recall\"]:.4f}')
print(f'  Target:     {r[\"target_accuracy\"]}')
print(f'  Meets target: {\"✅ YES\" if r[\"meets_target\"] else \"❌ NO\"} ')
print()
print('  Per-class AP@50:')
for c in r.get('per_class', []):
    print(f'    {c[\"class\"]:20s}  {c[\"ap50\"]:.4f}')
"
    echo ""
    echo "  Weights: runs/$PROJECT/weights/best.pt"
    echo ""
    echo "  To download to your Mac:"
    echo "    scp paperspace@<ip>:~/formdex/runs/$PROJECT/weights/best.pt ."
else
    echo "⚠️  Eval results not found — check logs above for errors."
    exit 1
fi

