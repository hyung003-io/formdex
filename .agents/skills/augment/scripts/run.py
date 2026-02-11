#!/usr/bin/env python3
"""Augment skill: generate synthetic training data variations with transformed labels.

Augmentations:
  1. Horizontal flip (mirror bbox x-coords)
  2. Brightness jitter (labels unchanged)
  3. Contrast jitter (labels unchanged)
  4. Noise injection (labels unchanged)
  5. Watermark overlay — semi-transparent text stamps (labels unchanged)
  6. Scan/fax resize — random DPI/aspect-ratio shift to simulate scanned pages
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent.parent))

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont
import numpy as np

from shared.utils import load_config

# ---------------------------------------------------------------------------
# Watermark text pool — common stamps seen on court / legal form copies
# ---------------------------------------------------------------------------
_WATERMARK_TEXTS = [
    "FILED", "COPY", "DRAFT", "ORIGINAL", "RECEIVED",
    "CONFORMED COPY", "SAMPLE", "NOT FOR FILING",
    "VOID", "DUPLICATE", "FAX", "SCANNED COPY",
]


def flip_horizontal(img: Image.Image, label_lines: list[str]) -> tuple[Image.Image, list[str]]:
    """Flip image horizontally and mirror bounding box x-coordinates."""
    flipped = img.transpose(Image.FLIP_LEFT_RIGHT)
    new_lines: list[str] = []
    for line in label_lines:
        parts = line.strip().split()
        if len(parts) != 5:
            continue
        cls, cx, cy, w, h = parts[0], float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])
        new_cx = 1.0 - cx
        new_lines.append(f"{cls} {new_cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
    return flipped, new_lines


def adjust_brightness(img: Image.Image, factor: float) -> Image.Image:
    """Adjust brightness by a factor (0.5-1.5 typical)."""
    enhancer = ImageEnhance.Brightness(img)
    return enhancer.enhance(factor)


def adjust_contrast(img: Image.Image, factor: float) -> Image.Image:
    """Adjust contrast by a factor."""
    enhancer = ImageEnhance.Contrast(img)
    return enhancer.enhance(factor)


def add_noise(img: Image.Image, intensity: float = 15.0) -> Image.Image:
    """Add Gaussian noise to image."""
    arr = np.array(img, dtype=np.float32)
    noise = np.random.normal(0, intensity, arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(arr)


def add_watermark(img: Image.Image) -> Image.Image:
    """Overlay a semi-transparent watermark stamp on the image.

    Simulates real-world scenarios where courts, clerks, or fax machines
    add stamps like "FILED", "COPY", "CONFORMED COPY" etc.
    """
    img = img.copy()
    w, h = img.size

    text = random.choice(_WATERMARK_TEXTS)
    # Random font size proportional to image width
    font_size = random.randint(int(w * 0.04), int(w * 0.10))

    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
    except Exception:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()

    # Create a transparent overlay
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Random rotation angle (-30 to 30 degrees)
    angle = random.uniform(-30, 30)

    # Random position — bias towards upper portion (where watermarks typically appear)
    tx = random.randint(int(w * 0.05), int(w * 0.6))
    ty = random.randint(int(h * 0.02), int(h * 0.35))

    # Random color and transparency
    colors = [
        (0, 0, 0),        # black
        (128, 128, 128),   # gray
        (200, 0, 0),       # red (common for stamps)
        (0, 0, 180),       # blue (common for stamps)
    ]
    color = random.choice(colors)
    alpha = random.randint(40, 120)  # semi-transparent

    # Draw text on a temporary image, rotate, then paste
    # Get text size
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    text_img = Image.new("RGBA", (tw + 20, th + 20), (0, 0, 0, 0))
    text_draw = ImageDraw.Draw(text_img)
    text_draw.text((10, 10), text, fill=(*color, alpha), font=font)

    # Add a border/outline for stamp effect (sometimes)
    if random.random() < 0.4:
        text_draw.rectangle(
            [2, 2, tw + 17, th + 17],
            outline=(*color, alpha),
            width=max(2, font_size // 15),
        )

    # Rotate
    text_img = text_img.rotate(angle, expand=True, resample=Image.BICUBIC)

    # Paste onto overlay
    overlay.paste(text_img, (tx, ty), text_img)

    # Composite
    img_rgba = img.convert("RGBA")
    result = Image.alpha_composite(img_rgba, overlay)
    return result.convert("RGB")


def resize_scan_fax(
    img: Image.Image,
    label_lines: list[str],
) -> tuple[Image.Image, list[str]]:
    """Simulate scan/fax size variations.

    Real-world scans and faxes come in at different DPIs and aspect ratios.
    This randomly resizes the image with slight aspect ratio distortion,
    then pads or crops back to a standard size.  Labels are adjusted to
    stay correct in the output coordinate space.
    """
    w, h = img.size

    # Random scale factor (simulating 150-300 DPI scans of the same page)
    scale = random.uniform(0.7, 1.3)
    # Slight aspect ratio distortion (fax machines often stretch vertically)
    aspect_jitter_x = random.uniform(0.95, 1.05)
    aspect_jitter_y = random.uniform(0.95, 1.05)

    new_w = max(64, int(w * scale * aspect_jitter_x))
    new_h = max(64, int(h * scale * aspect_jitter_y))

    resized = img.resize((new_w, new_h), Image.LANCZOS)

    # Pad or crop to original size
    canvas = Image.new("RGB", (w, h), (255, 255, 255))  # white background

    # Center the resized image on the canvas
    paste_x = (w - new_w) // 2
    paste_y = (h - new_h) // 2

    # Crop region from resized image that fits on canvas
    src_x0 = max(0, -paste_x)
    src_y0 = max(0, -paste_y)
    src_x1 = min(new_w, w - paste_x)
    src_y1 = min(new_h, h - paste_y)

    dst_x0 = max(0, paste_x)
    dst_y0 = max(0, paste_y)

    crop = resized.crop((src_x0, src_y0, src_x1, src_y1))
    canvas.paste(crop, (dst_x0, dst_y0))

    # Adjust labels — the bounding boxes shift and scale
    new_lines: list[str] = []
    for line in label_lines:
        parts = line.strip().split()
        if len(parts) != 5:
            continue
        cls = parts[0]
        cx, cy, bw, bh = float(parts[1]), float(parts[2]), float(parts[3]), float(parts[4])

        # Transform: original normalized → pixel → scaled → back to normalized on canvas
        px_cx = cx * w
        px_cy = cy * h
        px_bw = bw * w
        px_bh = bh * h

        # Apply scale + aspect jitter
        px_cx = px_cx * scale * aspect_jitter_x + paste_x
        px_cy = px_cy * scale * aspect_jitter_y + paste_y
        px_bw = px_bw * scale * aspect_jitter_x
        px_bh = px_bh * scale * aspect_jitter_y

        # Back to normalized
        new_cx = px_cx / w
        new_cy = px_cy / h
        new_bw = px_bw / w
        new_bh = px_bh / h

        # Clamp to valid range
        new_cx = max(0.001, min(0.999, new_cx))
        new_cy = max(0.001, min(0.999, new_cy))
        new_bw = max(0.001, min(0.999, new_bw))
        new_bh = max(0.001, min(0.999, new_bh))

        # Skip boxes that are mostly off-canvas
        if (new_cx - new_bw / 2 > 0.98) or (new_cx + new_bw / 2 < 0.02):
            continue
        if (new_cy - new_bh / 2 > 0.98) or (new_cy + new_bh / 2 < 0.02):
            continue

        new_lines.append(f"{cls} {new_cx:.6f} {new_cy:.6f} {new_bw:.6f} {new_bh:.6f}")

    return canvas, new_lines


def main() -> int:
    config = load_config()
    output_dir = Path(config.get("output_dir", "output"))
    frames_dir = output_dir / "frames"
    aug_dir = output_dir / "augmented"
    aug_dir.mkdir(parents=True, exist_ok=True)

    frames = sorted(frames_dir.glob("*.jpg"))
    labeled = [f for f in frames if f.with_suffix(".txt").exists()]

    if not labeled:
        print("[augment] No labeled frames found. Run label skill first.", file=sys.stderr)
        return 1

    print(f"[augment] Augmenting {len(labeled)} labeled frames...")
    count = 0

    for frame_path in labeled:
        label_path = frame_path.with_suffix(".txt")
        label_lines = label_path.read_text(encoding="utf-8").strip().split("\n")
        label_lines = [l for l in label_lines if l.strip()]

        img = Image.open(frame_path).convert("RGB")
        stem = frame_path.stem

        # 1. Horizontal flip
        flipped_img, flipped_labels = flip_horizontal(img, label_lines)
        out_img = aug_dir / f"{stem}_flip.jpg"
        out_lbl = aug_dir / f"{stem}_flip.txt"
        flipped_img.save(out_img, quality=95)
        out_lbl.write_text("\n".join(flipped_labels), encoding="utf-8")
        count += 1

        # 2. Brightness jitter (labels unchanged)
        brightness_factor = random.uniform(0.6, 1.4)
        bright_img = adjust_brightness(img, brightness_factor)
        out_img = aug_dir / f"{stem}_bright.jpg"
        out_lbl = aug_dir / f"{stem}_bright.txt"
        bright_img.save(out_img, quality=95)
        out_lbl.write_text("\n".join(label_lines), encoding="utf-8")
        count += 1

        # 3. Contrast jitter (labels unchanged)
        contrast_factor = random.uniform(0.7, 1.3)
        contrast_img = adjust_contrast(img, contrast_factor)
        out_img = aug_dir / f"{stem}_contrast.jpg"
        out_lbl = aug_dir / f"{stem}_contrast.txt"
        contrast_img.save(out_img, quality=95)
        out_lbl.write_text("\n".join(label_lines), encoding="utf-8")
        count += 1

        # 4. Noise injection (labels unchanged)
        noisy_img = add_noise(img)
        out_img = aug_dir / f"{stem}_noise.jpg"
        out_lbl = aug_dir / f"{stem}_noise.txt"
        noisy_img.save(out_img, quality=95)
        out_lbl.write_text("\n".join(label_lines), encoding="utf-8")
        count += 1

        # 5. Watermark overlay (labels unchanged — watermark is background noise)
        wm_img = add_watermark(img)
        out_img = aug_dir / f"{stem}_watermark.jpg"
        out_lbl = aug_dir / f"{stem}_watermark.txt"
        wm_img.save(out_img, quality=95)
        out_lbl.write_text("\n".join(label_lines), encoding="utf-8")
        count += 1

        # 6. Scan/fax resize (labels adjusted for new geometry)
        scan_img, scan_labels = resize_scan_fax(img, label_lines)
        out_img = aug_dir / f"{stem}_scanfax.jpg"
        out_lbl = aug_dir / f"{stem}_scanfax.txt"
        scan_img.save(out_img, quality=95)
        out_lbl.write_text("\n".join(scan_labels), encoding="utf-8")
        count += 1

    print(f"[augment] Generated {count} augmented samples in {aug_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
