# FormDex

Intelligent PDF form field detection, extraction, and analysis powered by YOLOv8.

## Quick Start (Interactive)
If the user wants to train a model, use the **formdex skill** (`.agents/skills/formdex/SKILL.md`).
Ask for: YouTube URL (or local video path), target classes, **labeling mode** (cua+sam / gemini / gpt / codex), optional accuracy target.
Then write to config.json (set `project` for named output in `runs/<project>/`) and run the pipeline.
If the user says `call subagent` for labeling, execute:
`bash .agents/skills/label/scripts/dispatch.sh [num_agents]`

## Quick Start (Autonomous)
If config.json is already populated, just run: `bash formdex.sh`

## Conventions
- Python with type hints, use `uv run` for execution
- Each skill in .agents/skills/ is independently runnable
- Use `codex exec --full-auto -C <path>` for parallel subagent dispatch
- Label modes: `cua+sam` (CUA clicks + SAM segmentation), `gemini` (native bbox), `gpt` (fallback), `codex` (subagent image-view mode, no API keys)
- YOLO model: yolov8n.pt (default, can be changed in config.json)

## Architecture
- Skills: formdex (intake), collect, label (parallel), augment, train, eval
- Shared code: shared/utils.py
- Config: config.json | Memory: progress.txt

## Output Directory
When `project` is set in config.json, output goes to `runs/<project>/` (e.g. `runs/subway-surfers/`).
When `project` is empty, falls back to `output_dir` (default `output/`).
All skills read `output_dir` from config — the `load_config()` helper resolves this automatically.

## Iteration Logic

Check `source_type` in config.json first:
- `"form"` → use the **Form Mode** iteration logic below
- anything else (or missing) → use the **Video Mode** (original) logic

### Form Mode (`source_type == "form"`)

1. **No frames** (frames/ empty or missing):
   → Run collect_form: `uv run .agents/skills/collect/scripts/collect_form.py`
   This downloads the PDF, fills it with synthetic data, renders to images, and auto-generates YOLO labels.
   Both collection AND labeling happen in this single step.

2. **Labels but no model** (weights/best.pt missing):
   → Run augment: `uv run .agents/skills/augment/scripts/run.py`
   → Run train: `uv run .agents/skills/train/scripts/run.py`

3. **Model but no eval** (eval_results.json missing):
   → Run eval: `uv run .agents/skills/eval/scripts/run.py`

4. **Eval exists, accuracy >= target**: → `<promise>COMPLETE</promise>`

5. **Eval exists, accuracy < target**:
   → Increase `num_variations` in config.json and re-run collect_form
   → Re-augment, re-train, re-evaluate

### Video Mode (original, `source_type != "form"`)

Check state and execute next phase (paths relative to output_dir):

1. **No video** (video.mp4 missing):
   → Run collect: `uv run .agents/skills/collect/scripts/run.py`

2. **No frames** (frames/ empty):
   → Run collect: `uv run .agents/skills/collect/scripts/run.py`

3. **Frames but no labels** (no .txt files in frames/):
   → Check `label_mode` in config.json:
     - `cua+sam`: `uv run .agents/skills/label/scripts/label_cua_sam.py`
     - `gemini`: `uv run .agents/skills/label/scripts/label_gemini.py`
     - `gpt` (parallel / subagent): `bash .agents/skills/label/scripts/dispatch.sh`
     - `codex` (parallel / no-key): `bash .agents/skills/label/scripts/dispatch.sh`
     - `gpt` (single): `uv run .agents/skills/label/scripts/run.py`

4. **Labels but no model** (weights/best.pt missing):
   → Run augment: `uv run .agents/skills/augment/scripts/run.py`
   → Run train: `uv run .agents/skills/train/scripts/run.py`

5. **Model but no eval** (eval_results.json missing):
   → Run eval: `uv run .agents/skills/eval/scripts/run.py`

6. **Eval exists, accuracy >= target**: → `<promise>COMPLETE</promise>`

7. **Eval exists, accuracy < target**:
   → Read failure analysis from eval_results.json
   → Re-label worst frames or collect more data
   → Re-train and re-evaluate

## After Each Phase
- Append learnings to progress.txt
- Commit: `git add -A && git commit -m "iter: [phase] - [description]"`
