<h1 align="center">FormDex</h1>

<div align="center">

![License: MIT](https://img.shields.io/badge/license-MIT-8ecaff?style=for-the-badge&labelColor=ffffff)
![PRs welcome](https://img.shields.io/badge/PRs-welcome-8ecaff?style=for-the-badge&labelColor=ffffff)

</div>

<div align="center">

Intelligent PDF form field detection, extraction, and analysis powered by YOLOv8. Upload a filled PDF — get back structured JSON data and annotated images with every field identified, text extracted, and checkboxes classified.

</div>

## architecture

```mermaid
flowchart LR
  A["data source (any unlabeled data)"] --> B["collect"]
  B --> C["label"]
  C --> D["augment"]
  D --> E["train"]
  E --> F["eval"]
  C -. "parallel subagents in git worktrees" .-> C
  F --> G{"meets target?"}
  G -- "no" --> C
  G -- "yes" --> H["complete"]
```

## components

- skills runtime: [codex skills](https://developers.openai.com/codex/skills/)
- pipeline skills: `collect`, `label`, `augment`, `train`, `eval`, `formdex`
- orchestration loop: `formdex.sh` + `AGENTS.md`
- shared helpers: `shared/utils.py`

## installation

```bash
git clone https://github.com/qtzx06/formdex && cd formdex
bash setup.sh
```

requirements:
- macos, linux, or windows
- python 3.11+
- [codex cli](https://github.com/openai/codex) (or the codex app)

## codex workflow (main path)

1. start codex in repo root
2. use the `formdex` skill to gather config
3. run labeling with subagents when needed
4. iterate until eval target is met

example:

```text
$ codex
> use the formdex skill to train a form field detector from this PDF: https://courts.ca.gov/...
> classes: player, weapon, vehicle
```

codex determines how many subagents to spawn for labeling based on the dataset size:

```bash
bash .agents/skills/label/scripts/dispatch.sh <n>
```

## run modes

autonomous loop:

```bash
bash formdex.sh
```

manual skills:

```bash
uv run .agents/skills/collect/scripts/run.py
bash .agents/skills/label/scripts/dispatch.sh 4
uv run .agents/skills/augment/scripts/run.py
uv run .agents/skills/train/scripts/run.py
uv run .agents/skills/eval/scripts/run.py
```

## config

minimal `config.json`:

```json
{
  "project": "my-project",
  "video_url": "https://youtube.com/watch?v=YOUR_VIDEO",
  "classes": ["player", "weapon", "vehicle"],
  "label_mode": "codex",
  "target_accuracy": 0.75,
  "num_agents": 4,
  "fps": 1,
  "yolo_model": "yolov8n.pt",
  "epochs": 50,
  "train_split": 0.8,
  "seed": 42
}
```

key fields:

| field | default | description |
|---|---|---|
| `project` | `""` | output namespace under `runs/<project>/` |
| `video_url` | `""` | youtube url or local video path |
| `classes` | `[]` | target classes |
| `label_mode` | `"codex"` | label strategy |
| `target_accuracy` | `0.75` | mAP@50 stop threshold |
| `num_agents` | `4` | parallel label workers |
| `fps` | `1` | extraction fps |
| `yolo_model` | `"yolov8n.pt"` | base yolo checkpoint |
| `epochs` | `50` | train epochs |
| `train_split` | `0.8` | train/val split |
| `seed` | `42` | deterministic split seed |

## outputs

- eval: `runs/<project>/eval_results.json`
- frames: `runs/<project>/frames/`
- label previews: `runs/<project>/frames/preview/`
- trained weights: `runs/<project>/weights/best.pt`

## repo layout

```text
formdex/
├── .agents/skills/
│   ├── formdex/
│   ├── collect/
│   ├── label/
│   ├── augment/
│   ├── train/
│   └── eval/
├── shared/utils.py
├── pipeline/main.py
├── docs/
├── formdex.sh
├── setup.sh
├── AGENTS.md
├── config.json
├── progress.txt
└── pyproject.toml
```

## docs

- [docs/usage.md](docs/usage.md)
- [docs/models.md](docs/models.md)
- [docs/skills.md](docs/skills.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/changelog.md](docs/changelog.md)

## contributing

contributions are welcome.

standard flow:

1. fork the repo and create a branch from `main`
2. keep changes scoped and explain the why in your pr
3. run relevant checks before opening the pr
4. open a pull request with:
   - clear summary
   - test/validation notes
   - screenshots/log snippets when relevant

if you’re planning a bigger change, open an issue first so we can align on direction.

## license

mit

---

<p align="center">made with love at openai ♡</p>
