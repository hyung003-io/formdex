# Paperspace Training Workflows

FormDex supports multiple workflows for using Paperspace GPUs. Choose based on whether you want to use agent-based labeling or programmatic labeling.

## Overview

| Workflow | Labeling | Speed | Cost | Best For |
|----------|----------|-------|------|----------|
| **Programmatic (Paperspace)** | PDF metadata | ⚡⚡⚡ Fastest | 💰 GPU only | Production, speed |
| **Vision (Hybrid)** | Codex agents (local) | ⚡⚡ Medium | 💰 GPU only | Testing vision accuracy |
| **Vision (API + Paperspace)** | GPT/Gemini (local) | ⚡ Slower | 💰💰 API + GPU | Best accuracy |

## ❌ What DOESN'T Work

**You CANNOT run Codex agents directly on Paperspace** because:
- Cursor is not installed on Paperspace (it's your Mac IDE)
- `codex exec` command doesn't exist on the remote machine
- No way to spawn Codex subagents remotely

## ✅ Workflow 1: Programmatic (All on Paperspace)

**Best for:** Fast, production pipelines where PDF metadata is accurate

### Setup

```json
{
  "form_label_mode": "programmatic"  // Uses PDF metadata
}
```

### Usage

```bash
# From your Mac, run everything on Paperspace
ssh paperspace@<your-ip> 'cd formdex && bash scripts/train_paperspace.sh'

# Or SSH in and run manually
ssh paperspace@<your-ip>
cd formdex
bash scripts/train_paperspace.sh
```

### What Happens

```
Paperspace GPU:
  1. collect_form → Renders images + generates labels from PDF
  2. augment      → Augments data
  3. train        → Trains on CUDA GPU (fast!)
  4. eval         → Evaluates model

↓ scp download ↓

Your Mac:
  best.pt (trained model)
```

### Pros & Cons

✅ **Pros:**
- Fastest workflow (everything on GPU machine)
- No local compute needed
- No API costs
- Single command

❌ **Cons:**
- Only works with fillable PDFs (needs AcroForm metadata)
- Can't test vision model accuracy
- No agent-based labeling

---

## ✅ Workflow 2: Vision with Codex (Hybrid) 🏆 RECOMMENDED FOR YOU

**Best for:** Testing vision-based labeling accuracy without API costs

### Setup

```json
{
  "form_label_mode": "vision",
  "label_mode": "codex",
  "num_agents": 4
}
```

### Usage

```bash
# One command does everything (label local, train remote)
bash scripts/train_paperspace_with_vision.sh paperspace@<your-ip>
```

### What Happens

```
Your Mac (local):
  1. collect_form → Renders images (no labels)
  2. dispatch.sh  → Spawns 4 Codex agents to label images
  3. augment      → Augments data

↓ rsync upload ↓

Paperspace GPU:
  4. train        → Trains on CUDA GPU (fast!)
  5. eval         → Evaluates model

↓ scp download ↓

Your Mac:
  best.pt (trained model)
```

### Pros & Cons

✅ **Pros:**
- Uses Codex agents (no API costs)
- Tests vision-based labeling accuracy
- Still gets GPU speed for training
- Automated workflow

❌ **Cons:**
- Requires local compute for labeling
- Takes longer (labeling on your Mac)
- Need good upload bandwidth
- Cursor must be running locally

---

## ✅ Workflow 3: Vision with API (Hybrid)

**Best for:** Maximum accuracy with GPT-4V, Gemini, or CUA+SAM

### Setup

```json
{
  "form_label_mode": "vision",
  "label_mode": "cua+sam",  // or "gemini" or "gpt"
}
```

Add API keys to `.env`:
```bash
OPENAI_API_KEY=sk-proj-...
# or
GEMINI_API_KEY=...
```

### Usage

```bash
# Label locally with API, then train on Paperspace
bash scripts/train_paperspace_with_vision.sh paperspace@<your-ip>
```

### What Happens

Same as Workflow 2, but uses external APIs instead of Codex.

### Pros & Cons

✅ **Pros:**
- Best labeling accuracy
- GPU-accelerated training
- Works even if Codex is unavailable

❌ **Cons:**
- API costs (especially CUA+SAM)
- Requires API keys
- Slowest workflow (API calls + upload)

---

## Manual Workflow (Step-by-Step)

If you prefer manual control:

### Step 1: Label Data Locally

```bash
# On your Mac
cd /Users/henryyung/projects/formdex

# Option A: Use Codex agents
bash .agents/skills/label/scripts/dispatch.sh 4

# Option B: Use programmatic (fast)
# Set form_label_mode: "programmatic" in config.json
# Then:
uv run .agents/skills/collect/scripts/collect_form.py
```

### Step 2: Upload to Paperspace

```bash
# Upload config + labeled data
rsync -avz config.json paperspace@<your-ip>:~/formdex/
rsync -avz runs/ud101-form/ paperspace@<your-ip>:~/formdex/runs/ud101-form/
```

### Step 3: Train on Paperspace

```bash
# SSH and train
ssh paperspace@<your-ip>
cd formdex
uv run .agents/skills/train/scripts/run.py
uv run .agents/skills/eval/scripts/run.py
```

### Step 4: Download Model

```bash
# From your Mac
scp paperspace@<your-ip>:~/formdex/runs/ud101-form/weights/best.pt .
```

---

## Comparison Summary

### Speed Ranking

1. **Programmatic (Paperspace only)** — 5-10 min total
2. **Vision + Codex (Hybrid)** — 15-30 min (depends on Mac speed)
3. **Vision + API (Hybrid)** — 20-40 min (API latency + upload)

### Cost Ranking

1. **Programmatic** — GPU time only (~$0.50/hr)
2. **Vision + Codex** — GPU time only (~$0.50/hr)
3. **Vision + API** — GPU + API costs (~$2-10 depending on mode)

### Accuracy Ranking (for vision-based)

1. **CUA+SAM** — Best (but expensive API)
2. **Codex** — Good (free)
3. **Gemini** — Good (cheap API)
4. **GPT** — Good (medium API cost)

### Programmatic vs Vision Accuracy

- **Programmatic** — Excellent for fillable PDFs (uses exact coordinates)
- **Vision** — Better for scanned/flattened PDFs or when testing AI models

---

## Recommendation for Your Setup

Based on your config (`label_mode: codex`, `form_label_mode: vision`):

```bash
# Use the hybrid workflow script
bash scripts/train_paperspace_with_vision.sh paperspace@<your-ip>
```

This will:
1. ✅ Label locally with Codex (no API costs)
2. ✅ Train on Paperspace GPU (fast)
3. ✅ Compare vision accuracy vs programmatic
4. ✅ Fully automated

**First run?** Try programmatic mode first to get a baseline:
```json
{
  "form_label_mode": "programmatic"
}
```

Then run `scripts/train_paperspace.sh` to see how accurate metadata-based labeling is. Then try vision mode to compare!

