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

# Checkbox bounding boxes in PDF forms are tiny (~10pt square → ~25px at 200 DPI).
# YOLO needs at least ~48-64px to reliably detect objects.  We pad checkbox labels
# so the detection target includes surrounding context (the label text, the box
# border, etc.) which makes the feature more distinctive.
CHECKBOX_PAD_FACTOR = 1.0  # expand each side by this multiple of the original size
                           # 1.0 → 3× total size (25px → ~75px), well within YOLO range

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

def random_text_for_class(cls: str, max_chars: int = 0) -> str:
    """Return a random plausible string for a given field class.

    When *max_chars* > 0 the returned text is padded/extended so it
    fills the available horizontal space, mimicking real-world forms
    where people write edge-to-edge.
    """
    if cls == "date_field":
        text = fake.date(pattern="%m/%d/%Y")
    elif cls == "dollar_amount":
        text = f"{random.randint(100, 15000)}.{random.randint(0, 99):02d}"
    elif cls == "case_number":
        text = f"{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}{random.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}-{random.randint(10000, 99999)}"
    elif cls == "signature":
        text = fake.name()
    else:
        # Generic text — could be name, address, etc.  Mix it up.
        generators = [
            fake.name,
            lambda: fake.address().replace("\n", ", "),
            fake.city,
            fake.state,
            fake.zipcode,
            fake.phone_number,
            lambda: fake.sentence(nb_words=4),
        ]
        text = random.choice(generators)()

    # Pad / extend text to fill the field's horizontal extent
    if max_chars > 0 and len(text) < max_chars:
        if cls == "text_field":
            # Add extra realistic content to fill the space
            while len(text) < max_chars:
                extra = random.choice([
                    f", {fake.city()}", f" {fake.state()}",
                    f" {fake.zipcode()}", f" {fake.street_address()}",
                    f", {fake.name()}", f" {fake.phone_number()}",
                ])
                text += extra
            text = text[:max_chars]  # trim to exact limit
        elif cls == "dollar_amount":
            # Pad with leading spaces or commas to fill
            text = text.rjust(max_chars)
        elif cls == "date_field":
            # Already fixed width, no padding needed
            pass

    return text


def _is_checkbox(widget: Any) -> bool:
    fts = (widget.field_type_string or "").lower()
    return fts in ("checkbox", "radiobutton", "button")


def _estimate_max_chars(widget: Any) -> int:
    """Estimate how many characters can fit in a widget based on its width.

    Uses a rough heuristic: ~6pt per character at typical form font sizes.
    This lets us fill fields edge-to-edge like real handwriting / typing.
    """
    rect = widget.rect
    field_width_pt = rect.width  # in PDF points
    # Average character width is ~5-7pt at 10-12pt font
    avg_char_width = 5.5
    return max(1, int(field_width_pt / avg_char_width))


def _draw_x_on_checkbox(page: Any, widget: Any) -> None:
    """Draw an 'X' mark inside a checkbox field rectangle.

    Real-world court forms use hand-drawn X marks, not checkmarks.
    This draws two diagonal lines to create an X inside the widget rect.
    """
    rect = widget.rect
    # Shrink slightly so the X is inside the box borders
    margin = min(rect.width, rect.height) * 0.15
    x0 = rect.x0 + margin
    y0 = rect.y0 + margin
    x1 = rect.x1 - margin
    y1 = rect.y1 - margin

    # Line thickness proportional to box size
    stroke_w = max(0.8, min(rect.width, rect.height) * 0.08)

    shape = page.new_shape()
    # Diagonal 1: top-left to bottom-right
    shape.draw_line(fitz.Point(x0, y0), fitz.Point(x1, y1))
    # Diagonal 2: top-right to bottom-left
    shape.draw_line(fitz.Point(x1, y0), fitz.Point(x0, y1))
    shape.finish(color=(0, 0, 0), width=stroke_w)
    shape.commit()


def fill_form_variation(
    doc: fitz.Document,
    field_meta: list[dict[str, Any]],
    fill_probability: float = 0.85,
) -> fitz.Document:
    """Fill form fields in *doc* with random synthetic data and return it.

    ``fill_probability`` controls how many fields are filled (rest stay empty)
    so the model sees partially-filled forms too.

    Checkboxes are marked with an X (matching real-world court form behavior)
    rather than a checkmark.  Text fields are filled to their maximum
    horizontal extent so the model learns to detect fully-filled fields.
    """
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        for widget in page.widgets():
            if random.random() > fill_probability:
                continue

            cls = classify_field(widget)

            if _is_checkbox(widget):
                # Checkbox / radio — randomly mark with X or leave empty
                check = random.choice([True, False])
                try:
                    if check:
                        # Draw an X mark (real-world court form style)
                        _draw_x_on_checkbox(page, widget)
                        # Also set the form value so PDF readers see it
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
                max_chars = _estimate_max_chars(widget)
                text = random_text_for_class(cls, max_chars=max_chars)
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
    skip_labels: bool = False,
) -> list[Path]:
    """Render each page of *doc* to a JPEG and write matching YOLO label files.

    Returns the list of image paths created.
    
    If skip_labels is True, only render images without generating label files
    (for vision-based labeling mode).
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

        # Build YOLO label lines (skip if vision mode)
        if not skip_labels:
            fields = page_fields.get(page_idx, [])
            lines: list[str] = []
            for f in fields:
                r = f["rect"]
                x0, y0, x1, y1 = r.x0, r.y0, r.x1, r.y1

                # Pad checkbox bounding boxes — they're too small for YOLO
                # to detect at their native ~10pt size.  Expanding the bbox
                # to include surrounding context (label text, borders) gives
                # YOLO a much bigger and more distinctive detection target.
                if f["class_name"] == "checkbox":
                    w_pt = x1 - x0
                    h_pt = y1 - y0
                    pad_x = w_pt * CHECKBOX_PAD_FACTOR
                    pad_y = h_pt * CHECKBOX_PAD_FACTOR
                    x0 = max(0, x0 - pad_x)
                    y0 = max(0, y0 - pad_y)
                    x1 = min(page_rect.width, x1 + pad_x)
                    y1 = min(page_rect.height, y1 + pad_y)

                line = pdf_rect_to_yolo(
                    field_x0=x0,
                    field_y0=y0,
                    field_x1=x1,
                    field_y1=y1,
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
    
    # Check form_label_mode: "programmatic" (default) or "vision"
    form_label_mode = config.get("form_label_mode", "programmatic").lower()
    skip_labels = form_label_mode == "vision"
    
    if skip_labels:
        print("[collect_form] Vision labeling mode — will render images without labels")
        print("[collect_form] Run the label skill after collection")

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
        images = render_and_label(doc, page_fields, frames_dir, var_idx, skip_labels=skip_labels)
        all_images.extend(images)
        doc.close()

        if (var_idx + 1) % 20 == 0 or var_idx == 0:
            print(f"  Generated variation {var_idx + 1}/{num_variations}")

    # Step 4: Write classes.txt (always, even in vision mode)
    classes_path = output_dir / "classes.txt"
    names = [name for name, _ in sorted(class_to_id.items(), key=lambda item: item[1])]
    classes_path.write_text("\n".join(names), encoding="utf-8")

    if skip_labels:
        print(f"[collect_form] Done. {len(all_images)} images (no labels) in {frames_dir}")
        print(f"[collect_form] Next: run label skill with label_mode={config.get('label_mode', 'codex')}")
    else:
        print(f"[collect_form] Done. {len(all_images)} images with labels in {frames_dir}")
    
    print(f"[collect_form] Classes ({len(class_to_id)}): {', '.join(names)}")
    print(f"[collect_form] Class map: {classes_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

