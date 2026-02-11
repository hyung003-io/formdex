# Form Labeling: Programmatic vs Vision

FormDex supports **two labeling strategies** for PDF forms, controlled by the `form_label_mode` config option.

## Comparison

| Strategy | Speed | Cost | API Key | Accuracy | Best For |
|----------|-------|------|---------|----------|----------|
| **Programmatic** | ⚡ Fast | 💰 Free | ❌ None | Good for fillable PDFs | Standard AcroForm PDFs with accurate metadata |
| **Vision** | 🐢 Slower | 💵 API costs | ✅ Required* | Better for complex/scanned forms | Scanned forms, XFA forms, or testing vision model performance |

\* Except when using `label_mode=codex` (no API key needed, uses Codex's built-in image viewing)

## How They Work

### Programmatic Labeling (`form_label_mode: "programmatic"`)

1. Downloads PDF
2. Reads AcroForm widget coordinates using PyMuPDF
3. Fills fields with synthetic data (Faker)
4. Renders to images at 200 DPI
5. Converts widget rectangles to YOLO format
6. **Output**: Images + labels in one step

**Pros:**
- ⚡ Fast (no API calls)
- 💰 Free (no API costs)
- 🎯 Pixel-perfect labels (uses PDF metadata)

**Cons:**
- Requires fillable PDFs with AcroForm metadata
- Won't work for scanned/flattened PDFs
- Assumes PDF metadata is accurate

### Vision Labeling (`form_label_mode: "vision"`)

1. Downloads PDF
2. Fills fields with synthetic data
3. Renders to images at 200 DPI
4. **Stops** (no labels generated)
5. Runs label skill with configured mode:
   - **CUA+SAM**: OpenAI CUA clicks + SAM segmentation
   - **Gemini**: Google Gemini native bbox detection
   - **GPT**: GPT-4V structured output
   - **Codex**: Codex agents with image viewing (no API key)

**Pros:**
- 🔍 Works on scanned/flattened PDFs
- 🤖 Can detect fields not in metadata
- 📊 Useful for comparing vision model accuracy

**Cons:**
- 🐢 Slower (API calls + processing)
- 💵 API costs (unless using Codex mode)
- 🎲 May miss fields or have bbox errors

## Configuration Examples

### Programmatic (Default)

```json
{
  "project": "ud101-programmatic",
  "source_type": "form",
  "form_url": "https://courts.ca.gov/.../ud101.pdf",
  "form_label_mode": "programmatic",
  "classes": ["text_field", "checkbox", "date_field", "dollar_amount", "signature", "case_number"],
  "num_variations": 100,
  "target_accuracy": 0.75
}
```

### Vision (Codex agents, no API key)

```json
{
  "project": "ud101-vision-codex",
  "source_type": "form",
  "form_url": "https://courts.ca.gov/.../ud101.pdf",
  "form_label_mode": "vision",
  "label_mode": "codex",
  "classes": ["text_field", "checkbox", "date_field", "dollar_amount", "signature", "case_number"],
  "num_variations": 100,
  "num_agents": 4,
  "target_accuracy": 0.75
}
```

### Vision (CUA+SAM, best accuracy)

```json
{
  "project": "ud101-vision-cuasam",
  "source_type": "form",
  "form_url": "https://courts.ca.gov/.../ud101.pdf",
  "form_label_mode": "vision",
  "label_mode": "cua+sam",
  "classes": ["text_field", "checkbox", "date_field", "dollar_amount", "signature", "case_number"],
  "num_variations": 100,
  "target_accuracy": 0.75
}
```

Requires `OPENAI_API_KEY` environment variable.

## Running a Comparison

Use the helper script to run both strategies on the same form and compare results:

```bash
bash scripts/compare_form_labeling.sh \
  "https://courts.ca.gov/.../ud101.pdf" \
  "ud101"
```

This will:
1. Train a model with programmatic labeling → `runs/ud101-programmatic/`
2. Train a model with vision labeling (Codex) → `runs/ud101-vision/`
3. Compare mAP@50, precision, recall
4. Declare a winner

Output example:

```
=== Results Comparison ===
Programmatic Labeling:
  mAP@50: 0.9234
  Precision: 0.9456
  Recall: 0.9123
  Meets target: True

Vision Labeling (Codex):
  mAP@50: 0.8876
  Precision: 0.9012
  Recall: 0.8934
  Meets target: True

Winner: Programmatic (by 0.0358 mAP@50)
```

## When to Use Each

### Use Programmatic When:
- ✅ You have fillable PDFs with AcroForm fields
- ✅ You want maximum speed and zero cost
- ✅ The PDF metadata is accurate and complete
- ✅ You're building a production pipeline

### Use Vision When:
- ✅ You have scanned or flattened PDFs
- ✅ The PDF has no AcroForm metadata
- ✅ You want to compare vision model performance
- ✅ You need to detect fields not in the PDF metadata
- ✅ You're experimenting with model accuracy

## Iteration Logic

Both modes follow the same augment → train → eval loop. The only difference is **how labels are generated**:

**Programmatic:**
```
collect_form (renders + labels) → augment → train → eval
```

**Vision:**
```
collect_form (renders only) → label skill → augment → train → eval
```

See `AGENTS.md` for full iteration logic.

