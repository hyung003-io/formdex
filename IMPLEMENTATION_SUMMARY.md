# Implementation Summary: Hybrid Form Labeling

## What Was Added

FormDex now supports **both programmatic and vision-based labeling** for PDF forms, allowing you to compare accuracy between metadata-based extraction and AI vision models.

## Changes Made

### 1. New Config Option: `form_label_mode`

**Location**: `config.json`

**Options**:
- `"programmatic"` (default) — Uses PDF AcroForm metadata to generate labels. Fast, free, no API keys.
- `"vision"` — Uses AI vision models/agents to label rendered images. Slower, may cost API fees (unless using Codex mode).

**Example (your current config)**:
```json
{
  "form_label_mode": "vision",
  "label_mode": "codex",
  "num_agents": 4
}
```

### 2. Updated `collect_form.py`

**Changes**:
- Added `skip_labels` parameter to `render_and_label()`
- Reads `form_label_mode` from config
- When `form_label_mode="vision"`:
  - Renders images without generating label files
  - Prints message directing user to run label skill next
- When `form_label_mode="programmatic"` (default):
  - Original behavior — renders images + generates labels in one step

**Location**: `.agents/skills/collect/scripts/collect_form.py`

### 3. Updated Iteration Logic

**Location**: `AGENTS.md`

**New Form Mode Logic**:
```
1. No frames → Run collect_form
   - programmatic: renders + labels
   - vision: renders only

2. Frames but no labels (vision mode only) → Run label skill
   - Supports: cua+sam, gemini, gpt, codex
   - Parallel dispatch via dispatch.sh

3. Labels but no model → augment + train
4. Model but no eval → eval
5. Eval meets target → COMPLETE
6. Eval below target → increase num_variations, repeat
```

### 4. Updated Documentation

**formdex SKILL.md** — Added Form Mode section with intake flow for both modes
**AGENTS.md** — Updated form iteration logic to support both labeling strategies
**docs/form_labeling_comparison.md** — New comprehensive comparison guide

### 5. Comparison Helper Script

**Location**: `scripts/compare_form_labeling.sh`

Runs both modes on the same form and compares results:
```bash
bash scripts/compare_form_labeling.sh \
  "https://courts.ca.gov/.../ud101.pdf" \
  "ud101"
```

Output: Side-by-side mAP@50, precision, recall comparison

### 6. Cleanup

Removed duplicate `yolodex/SKILL.md` (was identical to `formdex/SKILL.md`)

## How to Use

### Option 1: Vision Labeling (Your Current Config)

Your config is already set up for vision labeling with Codex agents:

```bash
# Clean start (if needed)
rm -rf runs/ud101-form output

# Run the pipeline
bash formdex.sh
```

**What will happen**:
1. `collect_form.py` downloads PDF, renders 100 variations (no labels)
2. `dispatch.sh` spawns 4 Codex agents to label images in parallel
3. Labels merged back to main repo
4. Augmentation, training, evaluation
5. Iterates until mAP@50 >= 0.75

**No API keys required** when using `label_mode: "codex"`

### Option 2: Programmatic Labeling (Fast, Free)

To compare, switch to programmatic mode:

```json
{
  "form_label_mode": "programmatic"
}
```

Then run:
```bash
bash formdex.sh
```

**What will happen**:
1. `collect_form.py` downloads PDF, renders 100 variations **with labels** (one step)
2. Augmentation, training, evaluation
3. Iterates until mAP@50 >= 0.75

Much faster since no vision model calls.

### Option 3: Side-by-Side Comparison

Use the comparison script:

```bash
bash scripts/compare_form_labeling.sh \
  "https://courts.ca.gov/sites/default/files/courts/default/2024-11/ud101.pdf" \
  "ud101"
```

Runs both modes sequentially and prints winner.

## Why Use Vision Labeling?

1. **Scanned PDFs**: Programmatic fails on scanned/flattened PDFs (no AcroForm metadata)
2. **Accuracy comparison**: Test if vision models outperform metadata-based extraction
3. **Missing metadata**: Some PDFs have incomplete or inaccurate field coordinates
4. **Research**: Compare CUA+SAM vs Gemini vs GPT vs Codex accuracy

## Current Setup

Your `config.json` is configured for:
- ✅ Form mode (`source_type: "form"`)
- ✅ Vision labeling (`form_label_mode: "vision"`)
- ✅ Codex agents (`label_mode: "codex"`, no API key needed)
- ✅ Parallel dispatch (`num_agents: 4`)

**Ready to run**: `bash formdex.sh`

## Files Modified

- `config.json` — Added `form_label_mode: "vision"`
- `.agents/skills/collect/scripts/collect_form.py` — Added vision mode support
- `AGENTS.md` — Updated form iteration logic
- `.agents/skills/formdex/SKILL.md` — Added form mode intake flow
- `docs/form_labeling_comparison.md` — New comparison guide
- `scripts/compare_form_labeling.sh` — New comparison script
- Deleted: `.agents/skills/yolodex/SKILL.md` (duplicate)

## Next Steps

1. **Test vision labeling**: Run `bash formdex.sh` with your current config
2. **Compare modes**: Run `bash scripts/compare_form_labeling.sh <form_url> <project_name>`
3. **Iterate**: Adjust `num_variations`, `num_agents`, or `label_mode` based on results

The system now fully supports **both programmatic and agent-based labeling** for forms, letting you compare which approach works best for your use case! 🎉

