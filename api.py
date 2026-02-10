#!/usr/bin/env python3
"""FastAPI service for detecting and extracting form fields from uploaded PDFs.

Accepts a filled PDF (any number of pages), runs YOLOv8 detection on every page,
extracts text via OCR, determines checkbox states, and returns structured JSON
plus annotated page images.

Usage:
    uv run uvicorn api:app --host 0.0.0.0 --port 8000

Endpoints:
    POST /extract          → JSON results + download URLs for annotated images
    GET  /files/{job}/{f}  → serve annotated images and crops
    GET  /health           → health check
    GET  /                 → interactive docs redirect
"""

from __future__ import annotations

import io
import shutil
import tempfile
import time
import uuid
from pathlib import Path

import fitz  # pymupdf
import numpy as np
import pytesseract
from fastapi import FastAPI, File, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from ultralytics import YOLO

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
WEIGHTS = ROOT / "runs" / "ud100-form" / "weights" / "best.pt"
CLASSES_FILE = ROOT / "runs" / "ud100-form" / "classes.txt"
JOBS_DIR = ROOT / "api_jobs"
JOBS_DIR.mkdir(exist_ok=True)

# ── Class colours (one per class) ──────────────────────────────────────────
COLORS = [
    (30, 144, 255),   # text_field    – dodger blue
    (0, 200, 83),     # checkbox      – green
    (255, 165, 0),    # date_field    – orange
    (220, 20, 60),    # dollar_amount – crimson
    (148, 103, 189),  # signature     – purple
    (0, 191, 255),    # case_number   – deep sky blue
]

# ── Load model once at startup ─────────────────────────────────────────────
model: YOLO | None = None
class_names: list[str] = []


def get_model() -> YOLO:
    global model
    if model is None:
        model = YOLO(str(WEIGHTS))
    return model


def get_class_names() -> list[str]:
    global class_names
    if not class_names:
        class_names = CLASSES_FILE.read_text().strip().splitlines()
    return class_names


# ── Fonts (loaded once) ───────────────────────────────────────────────────
def _load_fonts() -> tuple:
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 14)
        font_sm = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
        font_check = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
    except Exception:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 14)
            font_sm = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
            font_check = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 18)
        except Exception:
            font = ImageFont.load_default()
            font_sm = font
            font_check = font
    return font, font_sm, font_check


FONT, FONT_SM, FONT_CHECK = _load_fonts()

# ── Core logic ─────────────────────────────────────────────────────────────


def is_checkbox_checked(crop: Image.Image) -> bool:
    """Determine if a checkbox crop is checked by analyzing dark pixel density."""
    gray = ImageOps.grayscale(crop)
    w, h = gray.size
    mx = max(int(w * 0.2), 1)
    my = max(int(h * 0.2), 1)
    inner = gray.crop((mx, my, w - mx, h - my))
    arr = np.array(inner)
    return bool(np.mean(arr < 128) > 0.05)


def extract_text_from_crop(crop: Image.Image, field_class: str) -> str:
    """Run Tesseract OCR on a cropped field image."""
    w, h = crop.size
    scale = max(1, 150 // max(h, 1))
    if scale > 1:
        crop = crop.resize((w * scale, h * scale), Image.LANCZOS)
    gray = ImageOps.grayscale(crop)
    gray = gray.filter(ImageFilter.SHARPEN)
    if field_class in ("date_field", "dollar_amount", "case_number"):
        config = "--psm 7 -c tessedit_char_whitelist=0123456789/.-$,ABCDEFGHIJKLMNOPQRSTUVWXYZ "
    else:
        config = "--psm 7"
    try:
        text = pytesseract.image_to_string(gray, config=config).strip()
        return text.replace("|", "").replace("\\", "").strip()
    except Exception:
        return ""


def detect_on_image(img: Image.Image, conf: float) -> list[dict]:
    """Run YOLO on a PIL image and return raw detections."""
    # Save to a temp file for ultralytics
    tmp = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    img.save(tmp.name, quality=95)
    tmp.close()

    yolo = get_model()
    names = get_class_names()
    results = yolo.predict(source=tmp.name, conf=conf, verbose=False)
    Path(tmp.name).unlink(missing_ok=True)

    detections: list[dict] = []
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls_id = int(box.cls[0])
            detections.append({
                "class_id": cls_id,
                "class_name": names[cls_id] if cls_id < len(names) else f"class_{cls_id}",
                "confidence": round(float(box.conf[0]), 3),
                "bbox": [int(x1), int(y1), int(x2), int(y2)],
            })
    return detections


def annotate_page(
    img: Image.Image,
    detections: list[dict],
    crops_dir: Path,
    page_idx: int,
) -> tuple[Image.Image, list[dict]]:
    """Annotate one page image and extract field values.

    Returns (annotated_image, list_of_extracted_entries).
    """
    img = img.copy().convert("RGB")
    draw = ImageDraw.Draw(img)
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    class_counts: dict[str, int] = {}
    extracted: list[dict] = []

    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        cls_name = det["class_name"]
        conf = det["confidence"]
        cls_id = det["class_id"]
        color = COLORS[cls_id % len(COLORS)]

        crop = img.crop((x1, y1, x2, y2))
        class_counts[cls_name] = class_counts.get(cls_name, 0) + 1
        crop_name = f"p{page_idx}_{cls_name}_{class_counts[cls_name]:03d}.jpg"
        crop.save(crops_dir / crop_name)

        entry: dict = {
            "page": page_idx,
            "field_type": cls_name,
            "confidence": conf,
            "bbox": [x1, y1, x2, y2],
            "crop_file": crop_name,
        }

        if cls_name == "checkbox":
            checked = is_checkbox_checked(crop)
            entry["checked"] = checked
            entry["value"] = "✓ CHECKED" if checked else "☐ UNCHECKED"
        else:
            entry["value"] = extract_text_from_crop(crop, cls_name)

        extracted.append(entry)

        # ── Draw ───────────────────────────────────────────────────────
        if cls_name == "checkbox":
            pad = 6
            if entry.get("checked"):
                overlay_draw.rectangle(
                    [x1 - pad, y1 - pad, x2 + pad, y2 + pad],
                    fill=(0, 200, 83, 70), outline=(0, 200, 83, 255), width=3,
                )
                draw.text((x2 + 4, y1 - 4), "✓", fill=(0, 180, 60), font=FONT_CHECK)
                label = f"CHECKED {conf:.0%}"
                lbl_color = (0, 200, 83)
            else:
                overlay_draw.rectangle(
                    [x1 - pad, y1 - pad, x2 + pad, y2 + pad],
                    fill=(220, 20, 60, 50), outline=(220, 20, 60, 255), width=3,
                )
                draw.text((x2 + 4, y1 - 4), "✗", fill=(220, 20, 60), font=FONT_CHECK)
                label = f"UNCHECKED {conf:.0%}"
                lbl_color = (220, 20, 60)

            tb = draw.textbbox((x1, y1), label, font=FONT)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
            draw.rectangle([x1 - pad, y1 - pad - th - 6, x1 - pad + tw + 8, y1 - pad], fill=lbl_color)
            draw.text((x1 - pad + 3, y1 - pad - th - 4), label, fill="white", font=FONT)
        else:
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
            label = f"{cls_name} {conf:.0%}"
            tb = draw.textbbox((x1, y1), label, font=FONT)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
            draw.rectangle([x1, y1 - th - 4, x1 + tw + 6, y1], fill=color)
            draw.text((x1 + 2, y1 - th - 2), label, fill="white", font=FONT)

            if entry.get("value"):
                draw.text((x1 + 2, y2 + 2), entry["value"][:50], fill=color, font=FONT_SM)

    # Composite overlay
    img_rgba = img.convert("RGBA")
    img_rgba = Image.alpha_composite(img_rgba, overlay)
    return img_rgba.convert("RGB"), extracted


def process_pdf(pdf_bytes: bytes, conf: float, dpi: int) -> tuple[str, dict]:
    """Process all pages of a PDF and return (job_id, result_dict)."""
    job_id = uuid.uuid4().hex[:12]
    job_dir = JOBS_DIR / job_id
    job_dir.mkdir(parents=True)
    crops_dir = job_dir / "crops"
    crops_dir.mkdir()

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    num_pages = len(doc)

    all_extracted: list[dict] = []
    page_summaries: list[dict] = []
    annotated_files: list[str] = []

    t0 = time.time()

    for page_idx in range(num_pages):
        page = doc[page_idx]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)

        # Convert pixmap → PIL
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        # Detect
        detections = detect_on_image(img, conf=conf)

        # Annotate + extract
        annotated_img, page_extracted = annotate_page(img, detections, crops_dir, page_idx)

        # Save annotated page
        ann_name = f"page_{page_idx}.jpg"
        annotated_img.save(job_dir / ann_name, quality=95)
        annotated_files.append(ann_name)

        all_extracted.extend(page_extracted)

        # Per-page summary
        checkboxes = [e for e in page_extracted if e["field_type"] == "checkbox"]
        page_summaries.append({
            "page": page_idx,
            "total_fields": len(page_extracted),
            "checkboxes": len(checkboxes),
            "checked": sum(1 for c in checkboxes if c.get("checked")),
            "unchecked": sum(1 for c in checkboxes if not c.get("checked")),
            "text_fields": len([e for e in page_extracted if e["field_type"] != "checkbox"]),
            "annotated_image": f"/files/{job_id}/{ann_name}",
        })

    doc.close()
    elapsed = round(time.time() - t0, 2)

    # Overall summary
    all_checkboxes = [e for e in all_extracted if e["field_type"] == "checkbox"]
    result = {
        "job_id": job_id,
        "num_pages": num_pages,
        "total_fields": len(all_extracted),
        "total_checkboxes": len(all_checkboxes),
        "total_checked": sum(1 for c in all_checkboxes if c.get("checked")),
        "total_unchecked": sum(1 for c in all_checkboxes if not c.get("checked")),
        "processing_time_sec": elapsed,
        "pages": page_summaries,
        "fields": all_extracted,
    }

    # Save JSON to job dir too
    import json
    (job_dir / "results.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    return job_id, result


# ── FastAPI app ────────────────────────────────────────────────────────────

app = FastAPI(
    title="FormDex — PDF Form Field Extractor",
    description="Upload a filled PDF form → get structured extraction of every text field, "
                "checkbox state, date, dollar amount, signature, and case number.",
    version="1.0.0",
)


@app.get("/", include_in_schema=False)
async def root():
    """Redirect to interactive API docs."""
    return RedirectResponse(url="/docs")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model_loaded": model is not None,
        "weights": str(WEIGHTS),
        "classes": get_class_names(),
    }


@app.post("/extract")
async def extract_form(
    file: UploadFile = File(..., description="A filled PDF form"),
    conf: float = Query(0.25, ge=0.01, le=1.0, description="Detection confidence threshold"),
    dpi: int = Query(200, ge=72, le=600, description="Render DPI for PDF pages"),
):
    """Upload a filled PDF form and extract all form fields.

    Returns JSON with:
    - Per-page summaries (field counts, annotated image URLs)
    - Every detected field with: type, value/checked state, confidence, bbox
    - Links to annotated page images and individual field crops
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        return JSONResponse(
            status_code=400,
            content={"error": "Please upload a PDF file."},
        )

    pdf_bytes = await file.read()
    if len(pdf_bytes) < 100:
        return JSONResponse(
            status_code=400,
            content={"error": "File appears empty or too small."},
        )

    job_id, result = process_pdf(pdf_bytes, conf=conf, dpi=dpi)
    return result


@app.get("/files/{job_id}/{filename}")
async def serve_file(job_id: str, filename: str):
    """Serve annotated images and crop files for a given job."""
    # Check main job dir first, then crops subdir
    path = JOBS_DIR / job_id / filename
    if not path.exists():
        path = JOBS_DIR / job_id / "crops" / filename
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "File not found"})
    return FileResponse(path, media_type="image/jpeg")


@app.get("/files/{job_id}/crops/{filename}")
async def serve_crop(job_id: str, filename: str):
    """Serve individual cropped field images."""
    path = JOBS_DIR / job_id / "crops" / filename
    if not path.exists():
        return JSONResponse(status_code=404, content={"error": "Crop not found"})
    return FileResponse(path, media_type="image/jpeg")


# ── Run directly ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)

