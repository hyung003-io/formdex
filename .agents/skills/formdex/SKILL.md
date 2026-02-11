---
name: formdex
description: Train a custom YOLOv8 model to detect and extract form fields from PDF documents. Provide a PDF URL and target field classes, and this skill handles the entire pipeline autonomously — synthetic data generation, augmentation, training, and evaluation with iterative improvement.
user_invocable: true
---

## Intake Flow

FormDex supports **two modes**: Video (detect objects in gameplay/videos) and Form (detect fields in PDF forms).

### Video Mode

When the user wants to train a model on video/gameplay, gather:

1. **Video source** (required): YouTube URL or local file path (e.g. `/Users/me/Desktop/gameplay.mp4`)
2. **Project name** (required): Short kebab-case name (e.g. "subway-surfers", "fortnite-clips"). Output goes to `runs/<project>/`
3. **Target classes** (required): What objects to detect (e.g. "players, weapons, vehicles")
4. **Labeling mode** (required): Ask the user which labeling method to use:
   - **CUA+SAM** (recommended): OpenAI CUA clicks on objects, SAM segments precise boundaries. Best accuracy. Requires `OPENAI_API_KEY`.
   - **Gemini**: Google Gemini native bounding box detection. Fast, good accuracy. Requires `GEMINI_API_KEY`.
   - **GPT**: GPT vision model returns bounding boxes via structured output. Simple fallback. Requires `OPENAI_API_KEY`.
   - **Codex**: Codex subagents use built-in image viewing and write YOLO labels directly. No API keys.
5. **Target accuracy** (optional, default 0.75): mAP@50 threshold
6. **Parallel agents** (optional, default 4): How many labeling subagents (GPT/Codex parallel mode only)

### Form Mode

When the user wants to train a model on PDF forms, gather:

1. **Form URL** (required): URL or local path to a PDF form (e.g. `https://courts.ca.gov/.../ud101.pdf`)
2. **Project name** (required): Short kebab-case name (e.g. "ud101-form"). Output goes to `runs/<project>/`
3. **Target classes** (required): Form field types to detect (e.g. "text_field, checkbox, date_field, dollar_amount, signature, case_number")
4. **Form labeling strategy** (optional, default "programmatic"):
   - **Programmatic** (default): Fast, free. Uses PDF AcroForm metadata. No API keys or agents.
   - **Vision**: Uses agents/vision models to label (same modes as video). Allows comparison with vision-based detection.
5. **Labeling mode** (required only if form_label_mode=vision): Same as video mode (CUA+SAM, Gemini, GPT, Codex)
6. **Num variations** (optional, default 100): How many synthetic form variations to generate
7. **Target accuracy** (optional, default 0.75): mAP@50 threshold

## After Gathering Config

1. Write the values to `config.json`:

**Video Mode Example:**
```python
import json
config = json.load(open("config.json"))
config["project"] = "subway-surfers"  # output goes to runs/subway-surfers/
config["video_url"] = "<user's url or local path>"
config["classes"] = ["player", "weapon", ...]
config["label_mode"] = "cua+sam"  # or "gemini" or "gpt" or "codex"
config["target_accuracy"] = 0.75
config["num_agents"] = 4
json.dump(config, open("config.json", "w"), indent=2)
```

**Form Mode Example (Programmatic labeling):**
```python
import json
config = json.load(open("config.json"))
config["project"] = "ud101-form"
config["source_type"] = "form"
config["form_url"] = "https://courts.ca.gov/.../ud101.pdf"
config["classes"] = ["text_field", "checkbox", "date_field", "dollar_amount", "signature", "case_number"]
config["form_label_mode"] = "programmatic"  # fast, free
config["num_variations"] = 100
config["target_accuracy"] = 0.75
json.dump(config, open("config.json", "w"), indent=2)
```

**Form Mode Example (Vision labeling):**
```python
import json
config = json.load(open("config.json"))
config["project"] = "ud101-form-vision"
config["source_type"] = "form"
config["form_url"] = "https://courts.ca.gov/.../ud101.pdf"
config["classes"] = ["text_field", "checkbox", "date_field", "dollar_amount", "signature", "case_number"]
config["form_label_mode"] = "vision"  # use agents
config["label_mode"] = "codex"  # or "cua+sam", "gemini", "gpt"
config["num_variations"] = 100
config["num_agents"] = 4  # for parallel dispatch
config["target_accuracy"] = 0.75
json.dump(config, open("config.json", "w"), indent=2)
```

2. Then execute the pipeline phases in order by following the iteration logic in AGENTS.md:

**Video Mode:**
   - `uv run .agents/skills/collect/scripts/run.py`
   - Labeling (based on label_mode):
     - CUA+SAM: `uv run .agents/skills/label/scripts/label_cua_sam.py`
     - Gemini: `uv run .agents/skills/label/scripts/label_gemini.py`
     - GPT (parallel): `bash .agents/skills/label/scripts/dispatch.sh`
     - Codex (parallel): `bash .agents/skills/label/scripts/dispatch.sh`
     - GPT (single): `uv run .agents/skills/label/scripts/run.py`
   - `uv run .agents/skills/augment/scripts/run.py`
   - `uv run .agents/skills/train/scripts/run.py`
   - `uv run .agents/skills/eval/scripts/run.py`

**Form Mode (Programmatic):**
   - `uv run .agents/skills/collect/scripts/collect_form.py` (collection + labeling in one step)
   - `uv run .agents/skills/augment/scripts/run.py`
   - `uv run .agents/skills/train/scripts/run.py`
   - `uv run .agents/skills/eval/scripts/run.py`

**Form Mode (Vision):**
   - `uv run .agents/skills/collect/scripts/collect_form.py` (renders images only)
   - Run label skill (same as video mode)
   - `uv run .agents/skills/augment/scripts/run.py`
   - `uv run .agents/skills/train/scripts/run.py`
   - `uv run .agents/skills/eval/scripts/run.py`

3. Check `runs/<project>/eval_results.json` — if accuracy < target, re-label failures and retrain.

## Autonomous Mode

For fully autonomous execution, run: `bash formdex.sh`
This is a Ralph-style loop that iterates until target accuracy is reached.

## Prerequisites

- `OPENAI_API_KEY` environment variable (for CUA+SAM and GPT modes)
- `GEMINI_API_KEY` or `GOOGLE_API_KEY` (for Gemini mode)
- No API key required when using `label_mode=codex` + `dispatch.sh`
- `yt-dlp` and `ffmpeg` installed
- `uv` for Python dependency management
- `codex` CLI (optional, for parallel subagent dispatch)
