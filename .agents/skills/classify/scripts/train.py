#!/usr/bin/env python3
"""Train a MobileNetV3 classifier for checkbox state detection."""

from __future__ import annotations

import sys
from pathlib import Path

import torch
import torch.nn as nn
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
DATA_DIR = ROOT / "classify_data"
CHECKED_DIR = DATA_DIR / "checked"
UNCHECKED_DIR = DATA_DIR / "unchecked"
MODEL_PATH = DATA_DIR / "checkbox_classifier.pt"

class CheckboxDataset(Dataset):
    def __init__(self, image_paths: list[Path], labels: list[int], transform=None):
        self.image_paths = image_paths
        self.labels = labels
        self.transform = transform
    
    def __len__(self):
        return len(self.image_paths)
    
    def __getitem__(self, idx):
        img = Image.open(self.image_paths[idx]).convert("RGB")
        if self.transform:
            img = self.transform(img)
        return img, self.labels[idx]

def load_data():
    """Load and split data into train/val."""
    checked = list(CHECKED_DIR.glob("*.jpg"))
    unchecked = list(UNCHECKED_DIR.glob("*.jpg"))
    
    if len(checked) < 10 or len(unchecked) < 10:
        print(f"Error: Need at least 10 examples per class")
        print(f"  Checked: {len(checked)}")
        print(f"  Unchecked: {len(unchecked)}")
        sys.exit(1)
    
    # Combine and create labels (0=unchecked, 1=checked)
    all_paths = unchecked + checked
    all_labels = [0] * len(unchecked) + [1] * len(checked)
    
    # Shuffle
    import random
    combined = list(zip(all_paths, all_labels))
    random.shuffle(combined)
    all_paths, all_labels = zip(*combined)
    
    # Split 80/20
    split = int(0.8 * len(all_paths))
    train_paths, val_paths = list(all_paths[:split]), list(all_paths[split:])
    train_labels, val_labels = list(all_labels[:split]), list(all_labels[split:])
    
    print(f"Dataset:")
    print(f"  Train: {len(train_paths)} ({sum(train_labels)} checked)")
    print(f"  Val:   {len(val_paths)} ({sum(val_labels)} checked)")
    
    return train_paths, train_labels, val_paths, val_labels

def train_model(train_loader, val_loader, device, epochs=20):
    """Train MobileNetV3-small classifier."""
    # Load pretrained MobileNetV3
    model = models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
    
    # Replace classifier head for binary classification
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, 2)
    model = model.to(device)
    
    criterion = nn.CrossEntropyLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.001)
    
    best_acc = 0.0
    
    for epoch in range(epochs):
        # Train
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0
        
        for images, labels in train_loader:
            images, labels = images.to(device), labels.to(device)
            
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            
            train_loss += loss.item()
            _, predicted = outputs.max(1)
            train_total += labels.size(0)
            train_correct += predicted.eq(labels).sum().item()
        
        train_acc = 100. * train_correct / train_total
        
        # Validate
        model.eval()
        val_correct = 0
        val_total = 0
        
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                _, predicted = outputs.max(1)
                val_total += labels.size(0)
                val_correct += predicted.eq(labels).sum().item()
        
        val_acc = 100. * val_correct / val_total
        
        print(f"Epoch {epoch+1}/{epochs}: Train Acc={train_acc:.1f}%, Val Acc={val_acc:.1f}%")
        
        if val_acc > best_acc:
            best_acc = val_acc
            torch.save(model.state_dict(), MODEL_PATH)
            print(f"  ✅ Saved best model (val_acc={val_acc:.1f}%)")
    
    print(f"\n✅ Training complete! Best val accuracy: {best_acc:.1f}%")
    print(f"   Model saved to: {MODEL_PATH}")
    return model

def main() -> int:
    if not CHECKED_DIR.exists() or not UNCHECKED_DIR.exists():
        print("Error: Run collect_data.py first to label training data")
        return 1
    
    train_paths, train_labels, val_paths, val_labels = load_data()
    
    # Data transforms
    transform = transforms.Compose([
        transforms.Resize((64, 64)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    ])
    
    train_dataset = CheckboxDataset(train_paths, train_labels, transform)
    val_dataset = CheckboxDataset(val_paths, val_labels, transform)
    
    train_loader = DataLoader(train_dataset, batch_size=16, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=16, shuffle=False)
    
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Using device: {device}\n")
    
    train_model(train_loader, val_loader, device, epochs=20)
    
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

