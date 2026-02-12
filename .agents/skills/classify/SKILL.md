---
name: classify
description: Train a CNN classifier for checkbox state detection (checked vs unchecked). Uses MobileNetV3 for fast inference (~5-10ms per checkbox).
---

## Instructions

1. **Collect training data**: Manually label checkbox crops as checked/unchecked
   ```bash
   uv run .agents/skills/classify/scripts/collect_data.py
   ```
   - Reads checkbox crops from `api_jobs/*/crops/*checkbox*.jpg`
   - Shows each image, asks for label (c=checked, u=unchecked, s=skip)
   - Saves to `classify_data/checked/` and `classify_data/unchecked/`

2. **Train classifier**:
   ```bash
   uv run .agents/skills/classify/scripts/train.py
   ```
   - Trains MobileNetV3-small on labeled data
   - Outputs: `classify_data/checkbox_classifier.pt`
   - Shows accuracy on validation set

3. **Test classifier**:
   ```bash
   uv run .agents/skills/classify/scripts/test.py <image_path>
   ```

## Integration

Update `api.py` to use the classifier:
```python
from classify.scripts.inference import CheckboxClassifier

classifier = CheckboxClassifier("classify_data/checkbox_classifier.pt")

def is_checkbox_checked(crop: Image.Image) -> bool:
    return classifier.predict(crop)
```

## Requirements

- Minimum 50 labeled examples (25 checked, 25 unchecked)
- Recommended: 200+ examples for robustness

