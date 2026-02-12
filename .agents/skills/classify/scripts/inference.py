#!/usr/bin/env python3
"""Fast inference wrapper for checkbox classifier."""

from __future__ import annotations

from pathlib import Path

import torch
import torch.nn as nn
from PIL import Image
from torchvision import models, transforms


class CheckboxClassifier:
    """Fast checkbox state classifier using MobileNetV3."""
    
    def __init__(self, model_path: str | Path):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Load model
        self.model = models.mobilenet_v3_small(weights=None)
        self.model.classifier[3] = nn.Linear(self.model.classifier[3].in_features, 2)
        self.model.load_state_dict(torch.load(model_path, map_location=self.device))
        self.model = self.model.to(self.device)
        self.model.eval()
        
        # Transform
        self.transform = transforms.Compose([
            transforms.Resize((64, 64)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
        ])
    
    def predict(self, image: Image.Image) -> bool:
        """Predict if checkbox is checked.
        
        Args:
            image: PIL Image of checkbox crop
        
        Returns:
            True if checked, False if unchecked
        """
        # Convert to RGB if needed
        if image.mode != "RGB":
            image = image.convert("RGB")
        
        # Transform and add batch dimension
        img_tensor = self.transform(image).unsqueeze(0).to(self.device)
        
        # Predict
        with torch.no_grad():
            outputs = self.model(img_tensor)
            _, predicted = outputs.max(1)
        
        return bool(predicted.item() == 1)  # 1 = checked, 0 = unchecked
    
    def predict_with_confidence(self, image: Image.Image) -> tuple[bool, float]:
        """Predict with confidence score.
        
        Returns:
            (is_checked, confidence)
        """
        if image.mode != "RGB":
            image = image.convert("RGB")
        
        img_tensor = self.transform(image).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            outputs = self.model(img_tensor)
            probs = torch.softmax(outputs, dim=1)
            confidence, predicted = probs.max(1)
        
        return bool(predicted.item() == 1), float(confidence.item())


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python inference.py <checkbox_image.jpg>")
        sys.exit(1)
    
    model_path = Path(__file__).parent.parent.parent.parent.parent / "classify_data" / "checkbox_classifier.pt"
    if not model_path.exists():
        print(f"Error: Model not found at {model_path}")
        print("Run train.py first")
        sys.exit(1)
    
    classifier = CheckboxClassifier(model_path)
    img = Image.open(sys.argv[1])
    
    is_checked, conf = classifier.predict_with_confidence(img)
    result = "CHECKED" if is_checked else "UNCHECKED"
    print(f"{result} (confidence: {conf:.1%})")

