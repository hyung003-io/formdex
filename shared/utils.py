"""Shared utilities for the FormDex pipeline."""

from __future__ import annotations

import base64
import json
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class BoundingBox:
    class_name: str
    x: float
    y: float
    width: float
    height: float


class PipelineError(RuntimeError):
    """Raised when a pipeline step fails."""


def run_command(cmd: list[str]) -> None:
    """Run a subprocess command and raise with readable context on failure."""
    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError as exc:
        raise PipelineError(f"Required executable not found: {cmd[0]}") from exc
    except subprocess.CalledProcessError as exc:
        raise PipelineError(f"Command failed ({exc.returncode}): {' '.join(cmd)}") from exc


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def load_config(config_path: Path | None = None) -> dict[str, Any]:
    """Load config.json from the repo root. Resolves output_dir to runs/<project>/ when project is set."""
    if config_path is None:
        config_path = Path(__file__).resolve().parent.parent / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if config.get("project"):
        config["output_dir"] = f"runs/{config['project']}"
    return config


def encode_image_base64(image_path: Path) -> str:
    image_bytes = image_path.read_bytes()
    return base64.b64encode(image_bytes).decode("utf-8")


def extract_json_from_text(text: str) -> dict[str, Any]:
    """Parse JSON directly; fallback to extracting from markdown code fences."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise PipelineError("Model did not return valid JSON.")
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise PipelineError("Model returned malformed JSON.") from exc


def pdf_rect_to_yolo(
    field_x0: float,
    field_y0: float,
    field_x1: float,
    field_y1: float,
    page_width: float,
    page_height: float,
    img_width: int,
    img_height: int,
    class_id: int,
) -> str:
    """Convert a PDF field rectangle to a YOLO label line.

    pymupdf (fitz) already uses top-left origin coordinates, matching image
    pixel coordinates.  We just need to scale from PDF points to image pixels
    and then normalise to 0-1 for YOLO.

    Returns a YOLO-format string: ``class_id cx cy w h`` (all normalized 0-1).
    """
    scale_x = img_width / page_width
    scale_y = img_height / page_height

    # Map PDF rect to image pixels (same origin — top-left)
    img_x0 = field_x0 * scale_x
    img_y0 = field_y0 * scale_y
    img_x1 = field_x1 * scale_x
    img_y1 = field_y1 * scale_y

    # YOLO normalized center + size
    cx = clamp(((img_x0 + img_x1) / 2.0) / img_width, 0.0, 1.0)
    cy = clamp(((img_y0 + img_y1) / 2.0) / img_height, 0.0, 1.0)
    w = clamp(abs(img_x1 - img_x0) / img_width, 0.0, 1.0)
    h = clamp(abs(img_y1 - img_y0) / img_height, 0.0, 1.0)

    return f"{class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}"


def read_image_dimensions(frame_path: Path) -> tuple[int, int]:
    """Read width/height via ffprobe to avoid extra Python imaging deps."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height",
        "-of",
        "json",
        str(frame_path),
    ]
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except Exception as exc:  # noqa: BLE001
        raise PipelineError(f"Failed to read dimensions for {frame_path}") from exc
