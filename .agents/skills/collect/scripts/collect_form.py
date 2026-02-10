#!/usr/bin/env python3
"""Collect-form skill: download a PDF form, fill it with synthetic data,
render to images, and auto-generate YOLO labels from AcroForm field coordinates.

This replaces both the ``collect`` and ``label`` steps for PDF form pipelines.
"""

from __future__ import annotations

import random
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

import fitz  # pymupdf
from faker import Faker

# Ensure repo root is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from shared.utils import PipelineError, clamp, load_config, pdf_rect_to_yolo

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

RENDER_DPI = 200  # render resolution — higher = more detail but larger images

# Heuristic patterns to classify text fields more precisely
_DATE_PATTERNS = re.compile(r"(date|dob|birth|filed|entered)", re.I)
_DOLLAR_PATTERNS = re.compile(r"(amount|dollar|rent|cost|fee|price|damages|sum|payment|money|\$)", re.I)
_CASE_PATTERNS = re.compile(r"(case.*num|case.*no|docket|file.*num)", re.I)
_SIGNATURE_PATTERNS = re.compile(r"(sign|signature)", re.I)

fake = Faker()


# ---------------------------------------------------------------------------
# Field classification
# ---------------------------------------------------------------------------

def classify_field(widget: Any) -> str:
    """Map a pymupdf Widget to one of our YOLO class names.

    Uses ``widget.field_type_string`` (e.g. "CheckBox", "Text", "Button")
    which is reliable across pymupdf versions, rather than integer constants
    which vary.
    """
    fts = (widget.field_type_string or "").lower()
    name = (widget.field_name or "").lower()

    # Checkbox / radio button
    if fts in ("checkbox", "radiobutton"):
        return "checkbox"
    # Signature widget
    if fts == "signature" or _SIGNATURE_PATTERNS.search(name):
        return "signature"
    # Push buttons — not a fillable field, but label as checkbox for detection
    if fts == "button":
        return "checkbox"

    # Text or choice fields — refine by name heuristics
    if _CASE_PATTERNS.search(name):
        return "case_number"
    if _DATE_PATTERNS.search(name):
        return "date_field"
    if _DOLLAR_PATTERNS.search(name):
        return "dollar_amount"
    return "text_field"


# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------

def random_text_for_class(cls: str) -> str:
    """Return a random plausible string for a given field class."""
    if cls == "date_field":
        return fake.date(pattern="%m/%d/%Y")
    if cls == "dollar_amount":
        return f"{random.randint(100, 15000)}.{random.randint(0, 99):02d}"
    if cls == "case_number":
        return f"{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}-{random.randint(10000, 99999)}"
    if cls == "signature":
        return fake.name()
    # Generic text — could be name, address, etc.  Mix it up.
    generators = [
        fake.name,
        fake.address,
        fake.city,
        fake.state,
        fake.zipcode,
        fake.phone_number,
        lambda: fake.sentence(nb_words=4),
    ]
    return random.choice(generators)()


def _is_checkbox(widget: Any) -> bool:
    fts = (widget.field_type_string or "").lower()
    return fts in ("checkbox", "radiobutton", "button")


def fill_form_variation(
    doc: fitz.Document,
    field_meta: list[dict[str, Any]],
    fill_probability: float = 0.85,
) -> fitz.Document:
    """Fill form fields in *doc* with random synthetic data and return it.

    ``fill_probability`` controls how many fields are filled (rest stay empty)
    so the model sees partially-filled forms too.
    """
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        for widget in page.widgets():
            if random.random() > fill_probability:
                continue

            cls = classify_field(widget)

            if _is_checkbox(widget):
                # Checkbox / radio — randomly toggle on or off
                check = random.choice([True, False])
                try:
                    if check:
                        on = widget.on_state()
                        if on:
                            widget.field_value = on
                        else:
                            widget.field_value = "Yes"
                    else:
                        widget.field_value = "Off"
                    widget.update()
                except Exception:
                    pass
            elif cls == "signature":
                # Can't really fill signature fields programmatically
                pass
            else:
                text = random_text_for_class(cls)
                widget.field_value = text
                try:
                    widget.update()
                except Exception:
                    pass
    return doc


# ---------------------------------------------------------------------------
# PDF → images + YOLO labels
# ---------------------------------------------------------------------------

def extract_field_metadata(doc: fitz.Document, class_to_id: dict[str, int]) -> dict[int, list[dict[str, Any]]]:
    """Extract form field metadata from a PDF document.

    Returns a dict keyed by page index.  Each value is a list of dicts with
    ``class_name``, ``class_id``, and ``rect`` (fitz.Rect).
    """
    page_fields: dict[int, list[dict[str, Any]]] = {}

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        fields: list[dict[str, Any]] = []

        for widget in page.widgets():
            cls = classify_field(widget)
            if cls not in class_to_id:
                class_to_id[cls] = len(class_to_id)
            fields.append({
                "class_name": cls,
                "class_id": class_to_id[cls],
                "rect": widget.rect,
                "field_name": widget.field_name,
            })

        if fields:
            page_fields[page_idx] = fields

    return page_fields


def render_and_label(
    doc: fitz.Document,
    page_fields: dict[int, list[dict[str, Any]]],
    frames_dir: Path,
    variation_idx: int,
    dpi: int = RENDER_DPI,
) -> list[Path]:
    """Render each page of *doc* to a JPEG and write matching YOLO label files.

    Returns the list of image paths created.
    """
    created: list[Path] = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        page_rect = page.rect  # fitz.Rect — origin top-left, units = points

        # Render to pixmap
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = page.get_pixmap(matrix=mat)
        img_w, img_h = pix.width, pix.height

        img_name = f"form_{variation_idx:04d}_p{page_idx}.jpg"
        img_path = frames_dir / img_name
        pix.save(str(img_path))

        # Build YOLO label lines
        fields = page_fields.get(page_idx, [])
        lines: list[str] = []
        for f in fields:
            r = f["rect"]
            line = pdf_rect_to_yolo(
                field_x0=r.x0,
                field_y0=r.y0,
                field_x1=r.x1,
                field_y1=r.y1,
                page_width=page_rect.width,
                page_height=page_rect.height,
                img_width=img_w,
                img_height=img_h,
                class_id=f["class_id"],
            )
            lines.append(line)

        label_path = img_path.with_suffix(".txt")
        label_path.write_text("\n".join(lines), encoding="utf-8")
        created.append(img_path)

    return created


# ---------------------------------------------------------------------------
# Download helper
# ---------------------------------------------------------------------------

def download_pdf(url: str, dest: Path) -> Path:
    """Download a PDF from *url* to *dest*.  Handles file:// and http(s)://."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if Path(url).exists():
        import shutil
        shutil.copy2(url, dest)
    else:
        urllib.request.urlretrieve(url, dest)
    return dest


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> int:
    config = load_config()

    form_url = config.get("form_url", "")
    if not form_url:
        print("Error: form_url is empty in config.json", file=sys.stderr)
        return 1

    output_dir = Path(config.get("output_dir", "output"))
    frames_dir = output_dir / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)

    num_variations = int(config.get("num_variations", 100))
    classes_from_config: list[str] = config.get("classes", [])

    # Build initial class_to_id from config classes (preserves order)
    class_to_id: dict[str, int] = {}
    for cls in classes_from_config:
        normalized = cls.strip().lower().replace(" ", "_")
        if normalized and normalized not in class_to_id:
            class_to_id[normalized] = len(class_to_id)

    # Step 1: Download PDF
    pdf_path = output_dir / "form_template.pdf"
    if not pdf_path.exists():
        print(f"[collect_form] Downloading PDF from {form_url}...")
        try:
            download_pdf(form_url, pdf_path)
        except Exception as exc:
            raise PipelineError(f"Failed to download PDF: {exc}") from exc
    else:
        print(f"[collect_form] Using cached PDF: {pdf_path}")

    # Step 2: Open template and extract field metadata
    template_doc = fitz.open(str(pdf_path))
    if len(list(template_doc[0].widgets())) == 0:
        print(
            "[collect_form] Warning: No AcroForm widgets found in the PDF. "
            "The form may not be fillable or may use XFA.",
            file=sys.stderr,
        )

    page_fields = extract_field_metadata(template_doc, class_to_id)
    total_fields = sum(len(v) for v in page_fields.values())
    print(f"[collect_form] Found {total_fields} form fields across {len(page_fields)} page(s)")

    for pg_idx, fields in page_fields.items():
        by_class: dict[str, int] = {}
        for f in fields:
            by_class[f["class_name"]] = by_class.get(f["class_name"], 0) + 1
        summary = ", ".join(f"{k}: {v}" for k, v in sorted(by_class.items()))
        print(f"  Page {pg_idx}: {summary}")

    template_doc.close()

    # Step 3: Generate variations
    print(f"[collect_form] Generating {num_variations} synthetic variations...")
    all_images: list[Path] = []

    for var_idx in range(num_variations):
        doc = fitz.open(str(pdf_path))
        fill_prob = random.uniform(0.5, 1.0)  # vary fill completeness
        fill_form_variation(doc, [], fill_probability=fill_prob)
        images = render_and_label(doc, page_fields, frames_dir, var_idx)
        all_images.extend(images)
        doc.close()

        if (var_idx + 1) % 20 == 0 or var_idx == 0:
            print(f"  Generated variation {var_idx + 1}/{num_variations}")

    # Step 4: Write classes.txt
    classes_path = output_dir / "classes.txt"
    names = [name for name, _ in sorted(class_to_id.items(), key=lambda item: item[1])]
    classes_path.write_text("\n".join(names), encoding="utf-8")

    print(f"[collect_form] Done. {len(all_images)} images with labels in {frames_dir}")
    print(f"[collect_form] Classes ({len(class_to_id)}): {', '.join(names)}")
    print(f"[collect_form] Class map: {classes_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

