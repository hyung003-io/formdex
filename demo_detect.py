#!/usr/bin/env python3
"""Demo: generate a fresh test form and run the trained YOLOv8 model to
detect, extract text (OCR), and determine checkbox states.

Usage:
    uv run demo_detect.py                       # uses default UD-100 PDF
    uv run demo_detect.py --image my_scan.jpg   # run on any image/scan
    uv run demo_detect.py --pdf  some_form.pdf  # fill+render a different PDF

Output goes to  demo_output/  (annotated image, cropped elements, extracted_data.json).
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

import fitz  # pymupdf
import numpy as np
import pytesseract
from faker import Faker
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps
from ultralytics import YOLO

# ── Paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
WEIGHTS = ROOT / "runs" / "ud100-form" / "weights" / "best.pt"
CLASSES_FILE = ROOT / "runs" / "ud100-form" / "classes.txt"
FORM_TEMPLATE = ROOT / "runs" / "ud100-form" / "form_template.pdf"
DEMO_DIR = ROOT / "demo_output"

# ── Class colours (one per class) ──────────────────────────────────────────
COLORS = [
    (30, 144, 255),   # text_field    – dodger blue
    (0, 200, 83),     # checkbox      – green
    (255, 165, 0),    # date_field    – orange
    (220, 20, 60),    # dollar_amount – crimson
    (148, 103, 189),  # signature     – purple
    (0, 191, 255),    # case_number   – deep sky blue
]

fake = Faker()


# ── helpers ────────────────────────────────────────────────────────────────

def load_class_names() -> list[str]:
    return CLASSES_FILE.read_text().strip().splitlines()


def generate_test_form(pdf_path: Path, output_image: Path, dpi: int = 200) -> Path:
    """Fill a PDF form with random data and render page 0 as a JPEG."""
    doc = fitz.open(str(pdf_path))
    for page in doc:
        for widget in page.widgets():
            fts = (widget.field_type_string or "").lower()
            if fts in ("checkbox", "radiobutton", "button"):
                try:
                    if random.random() < 0.5:
                        on = widget.on_state()
                        widget.field_value = on if on else "Yes"
                    else:
                        widget.field_value = "Off"
                    widget.update()
                except Exception:
                    pass
            elif fts == "signature":
                pass
            else:
                name = (widget.field_name or "").lower()
                if "date" in name or "dob" in name:
                    widget.field_value = fake.date(pattern="%m/%d/%Y")
                elif "amount" in name or "dollar" in name or "rent" in name or "$" in name:
                    widget.field_value = f"{random.randint(500, 9999)}.{random.randint(0,99):02d}"
                elif "case" in name:
                    widget.field_value = f"BC-{random.randint(10000,99999)}"
                else:
                    widget.field_value = random.choice([
                        fake.name(), fake.address().replace("\n", ", "),
                        fake.city(), fake.phone_number(), fake.sentence(nb_words=3),
                    ])
                try:
                    widget.update()
                except Exception:
                    pass

    # Render page 0
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = doc[0].get_pixmap(matrix=mat)
    pix.save(str(output_image))
    doc.close()
    print(f"[demo] Test form rendered → {output_image}  ({pix.width}×{pix.height})")
    return output_image


# ── Checkbox state detection ───────────────────────────────────────────────

def is_checkbox_checked(crop: Image.Image) -> bool:
    """Determine if a checkbox crop is checked by analyzing dark pixel density
    in the interior region.

    A checked checkbox has significantly more dark ink (the X or ✓ mark)
    compared to an empty box that just has the border lines.
    """
    # Convert to grayscale
    gray = ImageOps.grayscale(crop)

    # Shrink to the inner ~60% to ignore the border
    w, h = gray.size
    margin_x = max(int(w * 0.2), 1)
    margin_y = max(int(h * 0.2), 1)
    inner = gray.crop((margin_x, margin_y, w - margin_x, h - margin_y))

    # Count dark pixels (ink) — threshold at 128
    arr = np.array(inner)
    dark_ratio = np.mean(arr < 128)

    # Checked boxes typically have 8-40% dark pixels inside;
    # empty boxes have < 3%
    return dark_ratio > 0.05


# ── OCR text extraction ───────────────────────────────────────────────────

def extract_text_from_crop(crop: Image.Image, field_class: str) -> str:
    """Run Tesseract OCR on a cropped field image and return cleaned text."""
    # Upscale small crops for better OCR accuracy
    w, h = crop.size
    scale = max(1, 150 // max(h, 1))
    if scale > 1:
        crop = crop.resize((w * scale, h * scale), Image.LANCZOS)

    # Preprocess: convert to grayscale, sharpen, binarize
    gray = ImageOps.grayscale(crop)
    gray = gray.filter(ImageFilter.SHARPEN)

    # Tesseract config based on field type
    if field_class in ("date_field", "dollar_amount", "case_number"):
        # Mostly digits, slashes, dashes, dots
        config = "--psm 7 -c tessedit_char_whitelist=0123456789/.-$,ABCDEFGHIJKLMNOPQRSTUVWXYZ "
    else:
        # General text
        config = "--psm 7"

    try:
        text = pytesseract.image_to_string(gray, config=config).strip()
        # Clean up common OCR artifacts
        text = text.replace("|", "").replace("\\", "").strip()
        return text
    except Exception:
        return ""


# ── Inference image size ──────────────────────────────────────────────────
# Must match training imgsz.  YOLO handles letterbox resizing internally;
# no pre-standardisation needed (avoids lossy double-resize).
_INFERENCE_IMGSZ = 1280  # keep in sync with config.json → imgsz


# ── YOLO detection ─────────────────────────────────────────────────────────

def run_detection(image_path: Path, conf: float = 0.25) -> list[dict]:
    """Run YOLOv8 inference and return a list of detections.

    The image is passed directly to YOLO which handles letterbox resizing
    internally (single resize, no quality loss).  Bounding boxes are
    returned in the original image coordinate space.
    """
    orig_img = Image.open(image_path).convert("RGB")
    orig_w, orig_h = orig_img.size
    img_np = np.array(orig_img)

    model = YOLO(str(WEIGHTS))
    results = model.predict(
        source=img_np,
        conf=conf,
        imgsz=_INFERENCE_IMGSZ,
        verbose=False,
    )

    class_names = load_class_names()

    detections: list[dict] = []
    for r in results:
        for box in r.boxes:
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            cls_id = int(box.cls[0])
            conf_val = float(box.conf[0])

            # Ultralytics maps boxes to original coords; just clamp.
            x1 = max(0, min(int(x1), orig_w))
            y1 = max(0, min(int(y1), orig_h))
            x2 = max(0, min(int(x2), orig_w))
            y2 = max(0, min(int(y2), orig_h))

            detections.append({
                "class_id": cls_id,
                "class_name": class_names[cls_id] if cls_id < len(class_names) else f"class_{cls_id}",
                "confidence": conf_val,
                "bbox": (x1, y1, x2, y2),
            })
    return detections


# ── Annotate, crop, and extract ────────────────────────────────────────────

def annotate_and_extract(
    image_path: Path,
    detections: list[dict],
    out_dir: Path,
) -> tuple[Path, list[dict]]:
    """Draw bounding boxes, crop each detection, run OCR / checkbox analysis.

    Returns (annotated_image_path, list_of_extracted_data).
    """
    img = Image.open(image_path).convert("RGB")
    draw = ImageDraw.Draw(img)

    # Semi-transparent overlay for checkbox state
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    overlay_draw = ImageDraw.Draw(overlay)

    # Try to get a nice font
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

    crops_dir = out_dir / "crops"
    crops_dir.mkdir(parents=True, exist_ok=True)

    class_counts: dict[str, int] = {}
    extracted: list[dict] = []

    for det in detections:
        x1, y1, x2, y2 = det["bbox"]
        cls_name = det["class_name"]
        conf = det["confidence"]
        cls_id = det["class_id"]
        color = COLORS[cls_id % len(COLORS)]

        # Crop the element
        crop = img.crop((x1, y1, x2, y2))
        class_counts[cls_name] = class_counts.get(cls_name, 0) + 1
        crop_name = f"{cls_name}_{class_counts[cls_name]:03d}.jpg"
        crop.save(crops_dir / crop_name)

        # ── Extract value ──────────────────────────────────────────────
        entry: dict = {
            "field_type": cls_name,
            "confidence": round(conf, 3),
            "bbox": [x1, y1, x2, y2],
            "crop_file": crop_name,
        }

        if cls_name == "checkbox":
            checked = bool(is_checkbox_checked(crop))
            entry["checked"] = checked
            entry["value"] = "✓ CHECKED" if checked else "☐ UNCHECKED"
        else:
            text = extract_text_from_crop(crop, cls_name)
            entry["value"] = text

        extracted.append(entry)

        # ── Draw on annotated image ────────────────────────────────────
        if cls_name == "checkbox":
            # Make checked vs unchecked VERY visually distinct
            pad = 6  # padding around the checkbox for the highlight
            if entry.get("checked"):
                # GREEN semi-transparent fill + thick green border + checkmark
                overlay_draw.rectangle(
                    [x1 - pad, y1 - pad, x2 + pad, y2 + pad],
                    fill=(0, 200, 83, 70),         # green tint
                    outline=(0, 200, 83, 255),
                    width=3,
                )
                # Draw a bold ✓ next to the checkbox
                draw.text((x2 + 4, y1 - 4), "✓", fill=(0, 180, 60), font=font_check)
                # Label
                label = f"CHECKED {conf:.0%}"
                lbl_color = (0, 200, 83)
            else:
                # RED semi-transparent fill + thick red border + X
                overlay_draw.rectangle(
                    [x1 - pad, y1 - pad, x2 + pad, y2 + pad],
                    fill=(220, 20, 60, 50),         # red tint
                    outline=(220, 20, 60, 255),
                    width=3,
                )
                # Draw a bold ✗ next to the checkbox
                draw.text((x2 + 4, y1 - 4), "✗", fill=(220, 20, 60), font=font_check)
                # Label
                label = f"UNCHECKED {conf:.0%}"
                lbl_color = (220, 20, 60)

            # Label above the box
            text_bbox_lbl = draw.textbbox((x1, y1), label, font=font)
            tw = text_bbox_lbl[2] - text_bbox_lbl[0]
            th = text_bbox_lbl[3] - text_bbox_lbl[1]
            draw.rectangle([x1 - pad, y1 - pad - th - 6, x1 - pad + tw + 8, y1 - pad], fill=lbl_color)
            draw.text((x1 - pad + 3, y1 - pad - th - 4), label, fill="white", font=font)
        else:
            # Non-checkbox fields: normal colored box + label
            draw.rectangle([x1, y1, x2, y2], outline=color, width=2)
            label = f"{cls_name} {conf:.0%}"
            text_bbox_lbl = draw.textbbox((x1, y1), label, font=font)
            tw = text_bbox_lbl[2] - text_bbox_lbl[0]
            th = text_bbox_lbl[3] - text_bbox_lbl[1]
            draw.rectangle([x1, y1 - th - 4, x1 + tw + 6, y1], fill=color)
            draw.text((x1 + 2, y1 - th - 2), label, fill="white", font=font)

        # For text fields, show extracted text below the box
        if cls_name != "checkbox" and entry.get("value"):
            val_preview = entry["value"][:50]
            draw.text((x1 + 2, y2 + 2), val_preview, fill=color, font=font_sm)

    # Composite the semi-transparent checkbox overlays onto the image
    img_rgba = img.convert("RGBA")
    img_rgba = Image.alpha_composite(img_rgba, overlay)
    img_final = img_rgba.convert("RGB")

    annotated_path = out_dir / "annotated.jpg"
    img_final.save(annotated_path, quality=95)
    return annotated_path, extracted


# ── Pretty printing ───────────────────────────────────────────────────────

def print_results(extracted: list[dict]) -> None:
    """Print a structured summary of all extracted form data."""
    # Group by type
    checkboxes = [e for e in extracted if e["field_type"] == "checkbox"]
    text_fields = [e for e in extracted if e["field_type"] not in ("checkbox",)]

    checked_count = sum(1 for c in checkboxes if c.get("checked"))
    unchecked_count = len(checkboxes) - checked_count

    print(f"\n{'═' * 70}")
    print(f"  EXTRACTED FORM DATA")
    print(f"{'═' * 70}")

    # Checkboxes
    print(f"\n  📋 CHECKBOXES ({len(checkboxes)} found — {checked_count} checked, {unchecked_count} unchecked)")
    print(f"  {'─' * 60}")
    for i, cb in enumerate(checkboxes, 1):
        state = "✓ CHECKED  " if cb.get("checked") else "☐ UNCHECKED"
        x1, y1, x2, y2 = cb["bbox"]
        print(f"    {i:2d}. {state}   (conf={cb['confidence']:.0%}, pos=({x1},{y1}))")

    # Text-based fields
    for field_type in ["text_field", "date_field", "dollar_amount", "case_number", "signature"]:
        fields = [e for e in text_fields if e["field_type"] == field_type]
        if not fields:
            continue
        icon = {"text_field": "📝", "date_field": "📅", "dollar_amount": "💲",
                "case_number": "📁", "signature": "✍️"}.get(field_type, "📄")
        print(f"\n  {icon} {field_type.upper().replace('_', ' ')}S ({len(fields)} found)")
        print(f"  {'─' * 60}")
        for i, f in enumerate(fields, 1):
            val = f["value"] if f["value"] else "(empty)"
            val_display = val[:55]
            if len(val) > 55:
                val_display += "…"
            print(f"    {i:2d}. {val_display:<58s} (conf={f['confidence']:.0%})")

    print(f"\n{'═' * 70}\n")


# ── main ───────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Demo: detect & extract form fields with trained YOLOv8")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--image", type=str, help="Path to an existing image/scan to run detection on")
    group.add_argument("--pdf", type=str, help="Path to a PDF form to fill, render, and detect")
    parser.add_argument("--conf", type=float, default=0.25, help="Confidence threshold (default: 0.25)")
    parser.add_argument("--page", type=int, default=0, help="Page index to render (default: 0)")
    args = parser.parse_args()

    if not WEIGHTS.exists():
        print(f"Error: Model weights not found at {WEIGHTS}", file=sys.stderr)
        print("Train first or download best.pt from Paperspace.", file=sys.stderr)
        return 1

    DEMO_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: Get or create the test image
    if args.image:
        test_image = Path(args.image)
        if not test_image.exists():
            print(f"Error: Image not found: {test_image}", file=sys.stderr)
            return 1
        print(f"[demo] Using provided image: {test_image}")
    else:
        pdf_path = Path(args.pdf) if args.pdf else FORM_TEMPLATE
        if not pdf_path.exists():
            print(f"Error: PDF not found: {pdf_path}", file=sys.stderr)
            return 1
        test_image = DEMO_DIR / "test_form.jpg"
        generate_test_form(pdf_path, test_image)

    # Step 2: Run YOLO detection
    print(f"[demo] Running YOLOv8 detection (conf ≥ {args.conf:.0%})...")
    detections = run_detection(test_image, conf=args.conf)
    print(f"[demo] Detected {len(detections)} elements")

    # Step 3: Annotate + extract text / checkbox states
    print(f"[demo] Extracting text (OCR) and checkbox states...")
    annotated, extracted = annotate_and_extract(test_image, detections, DEMO_DIR)
    print(f"[demo] Annotated image → {annotated}")
    print(f"[demo] Cropped elements → {DEMO_DIR / 'crops'}/")

    # Step 4: Save structured data as JSON
    json_path = DEMO_DIR / "extracted_data.json"
    json_path.write_text(json.dumps(extracted, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[demo] Structured data  → {json_path}")

    # Step 5: Print results
    print_results(extracted)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
