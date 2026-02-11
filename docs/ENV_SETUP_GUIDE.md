# Environment Setup Guide

## Current Status

Your `.env` file exists but has a syntax error:
```
Error: openapi_key: command not found
```

This means the file is missing the `=` sign or has incorrect variable names.

## ✅ Good News: You Don't Need API Keys!

Since your `config.json` is set to:
```json
{
  "form_label_mode": "vision",
  "label_mode": "codex"
}
```

**Codex mode doesn't require any API keys!** It uses Codex's built-in image viewing.

## 🔧 Fix Your .env File (Optional)

If you want to try other modes (CUA+SAM, Gemini, GPT), fix your `.env` file:

### Correct Format

```bash
# FormDex Environment Variables

# OpenAI (for CUA+SAM and GPT modes)
OPENAI_API_KEY=sk-proj-your-key-here

# Gemini (for Gemini mode)
GEMINI_API_KEY=your-gemini-key-here
# OR
GOOGLE_API_KEY=your-google-key-here
```

### Steps to Fix

1. Open your `.env` file:
   ```bash
   nano .env
   # or
   code .env
   ```

2. Make sure it follows the format above:
   - Variable names must be UPPERCASE
   - Must have `=` between variable name and value
   - No spaces around `=`
   - One variable per line

3. If you have keys, paste them after the `=`
4. If you DON'T have keys yet, you can leave the file empty or comment out the lines

### Example of Common Mistakes

❌ **Wrong:**
```bash
openapi_key sk-proj-...          # lowercase, no =
OPENAI_API_KEY: sk-proj-...      # colon instead of =
OPENAI_API_KEY = sk-proj-...     # spaces around =
```

✅ **Correct:**
```bash
OPENAI_API_KEY=sk-proj-...
```

## 🎯 Your Current Setup (Codex Mode)

**You're ready to run without any API keys!**

```bash
bash formdex.sh
```

This will:
1. Download and render PDF forms
2. Use Codex agents to label images (built-in vision, no API needed)
3. Train YOLO model
4. Evaluate results

## 🔑 Getting API Keys (Optional)

Only needed if you want to try other labeling modes:

### OpenAI (for CUA+SAM or GPT mode)
1. Go to: https://platform.openai.com/api-keys
2. Create new secret key
3. Copy key (starts with `sk-proj-...`)
4. Add to `.env`: `OPENAI_API_KEY=sk-proj-...`

### Gemini (for Gemini mode)
1. Go to: https://aistudio.google.com/app/apikey
2. Create API key
3. Copy key
4. Add to `.env`: `GEMINI_API_KEY=your-key-here`

## 🧪 Test Your Setup

Run the environment checker:

```bash
bash scripts/check_env.sh
```

This will tell you:
- ✅ Which API keys are set
- ✅ Which modes are available
- ✅ If required tools are installed
- ✅ If your config is valid

## 📊 Mode Comparison

| Mode | API Key | Cost | When to Use |
|------|---------|------|-------------|
| **codex** (your current) | ❌ None | 💰 Free | Default, no setup needed |
| **programmatic** | ❌ None | 💰 Free | Fastest, uses PDF metadata |
| **gemini** | ✅ GEMINI_API_KEY | 💰 Low | Fast vision, native bboxes |
| **gpt** | ✅ OPENAI_API_KEY | 💰💰 Medium | Good fallback |
| **cua+sam** | ✅ OPENAI_API_KEY | 💰💰💰 High | Best accuracy |

## 🚀 Quick Start (No API Keys)

Since you're using Codex mode, just run:

```bash
# Fix your .env first (or delete it if empty)
rm .env  # if it's empty/broken

# Then run the pipeline
bash formdex.sh
```

## 💡 Recommendation

1. **First run**: Use your current setup (`label_mode: codex`) — no API keys needed
2. **After first run**: If accuracy is low, try `form_label_mode: programmatic` (even faster, still free)
3. **For comparison**: Get API keys and try `label_mode: cua+sam` to see if vision models do better

## 🆘 Troubleshooting

**Error: "OPENAI_API_KEY not set"**
- You switched to a mode that needs API keys
- Either add keys to `.env` OR switch back to `label_mode: codex`

**Error: "command not found" from .env**
- Fix syntax in `.env` file (see "Correct Format" above)
- Or delete `.env` if you don't need API keys yet

**Error: "codex not found"**
- Install Codex CLI: https://cursor.sh/docs
- Or use single-agent mode: `num_agents: 1`

