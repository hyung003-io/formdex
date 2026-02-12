#!/usr/bin/env python3
"""Interactive tool to label checkbox crops for training a classifier."""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from PIL import Image

# Find all checkbox crops
ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
API_JOBS = ROOT / "api_jobs"
OUTPUT_DIR = ROOT / "classify_data"
CHECKED_DIR = OUTPUT_DIR / "checked"
UNCHECKED_DIR = OUTPUT_DIR / "unchecked"

def collect_checkboxes() -> list[Path]:
    """Find all checkbox crop images."""
    return sorted(API_JOBS.glob("*/crops/*checkbox*.jpg"))

def show_and_label(image_path: Path) -> str | None:
    """Show image and get user label.
    
    Returns:
        'checked', 'unchecked', or None (skip)
    """
    img = Image.open(image_path)
    img.show()
    
    print(f"\n{image_path.name}")
    print("  [c] Checked")
    print("  [u] Unchecked")
    print("  [s] Skip")
    print("  [q] Quit")
    
    while True:
        choice = input("Label: ").strip().lower()
        if choice == 'c':
            return 'checked'
        elif choice == 'u':
            return 'unchecked'
        elif choice == 's':
            return None
        elif choice == 'q':
            sys.exit(0)
        else:
            print("Invalid choice. Use c/u/s/q")

def main() -> int:
    CHECKED_DIR.mkdir(parents=True, exist_ok=True)
    UNCHECKED_DIR.mkdir(parents=True, exist_ok=True)
    
    checkboxes = collect_checkboxes()
    if not checkboxes:
        print("No checkbox crops found in api_jobs/")
        return 1
    
    print(f"Found {len(checkboxes)} checkbox crops")
    print("Label each as checked (c) or unchecked (u)\n")
    
    checked_count = len(list(CHECKED_DIR.glob("*.jpg")))
    unchecked_count = len(list(UNCHECKED_DIR.glob("*.jpg")))
    
    for i, checkbox_path in enumerate(checkboxes, 1):
        # Skip if already labeled
        if (CHECKED_DIR / checkbox_path.name).exists():
            continue
        if (UNCHECKED_DIR / checkbox_path.name).exists():
            continue
        
        print(f"\n[{i}/{len(checkboxes)}] Current: {checked_count} checked, {unchecked_count} unchecked")
        
        label = show_and_label(checkbox_path)
        
        if label == 'checked':
            shutil.copy2(checkbox_path, CHECKED_DIR / checkbox_path.name)
            checked_count += 1
        elif label == 'unchecked':
            shutil.copy2(checkbox_path, UNCHECKED_DIR / checkbox_path.name)
            unchecked_count += 1
    
    print(f"\n✅ Labeling complete!")
    print(f"   Checked: {checked_count}")
    print(f"   Unchecked: {unchecked_count}")
    print(f"   Total: {checked_count + unchecked_count}")
    
    if checked_count + unchecked_count < 50:
        print("\n⚠️  Warning: < 50 examples. Recommend 100+ for good accuracy.")
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

