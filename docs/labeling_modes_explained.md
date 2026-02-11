# Labeling Modes Explained

There's important confusion about "agents" vs "API calls" — let's clarify what works where.

## Types of Labeling

### 1. Programmatic (No AI)

```json
{
  "form_label_mode": "programmatic"
}
```

**What it is:** Reads PDF AcroForm metadata (field coordinates) directly

**Works on:**
- ✅ Your Mac
- ✅ Paperspace
- ✅ Any Linux server

**Requires:**
- ❌ No API keys
- ❌ No Cursor
- ❌ No internet (for labeling)

**Speed:** ⚡⚡⚡ Instant (just reads PDF metadata)

**Command:**
```bash
uv run .agents/skills/collect/scripts/collect_form.py
```

---

### 2. Codex Agents (Parallel Subagents)

```json
{
  "form_label_mode": "vision",
  "label_mode": "codex",
  "num_agents": 4
}
```

**What it is:** Spawns 4 Cursor AI instances in parallel using `codex exec` command. Each subagent views images and writes labels.

**Works on:**
- ✅ Your Mac (with Cursor installed)
- ❌ Paperspace (no Cursor)
- ❌ Linux servers (no Cursor)

**Requires:**
- ❌ No API keys
- ✅ Cursor IDE installed
- ✅ `codex` CLI available

**Speed:** ⚡⚡ Medium (parallel processing on your Mac)

**Command:**
```bash
bash .agents/skills/label/scripts/dispatch.sh 4
```

**What happens internally:**
```bash
# dispatch.sh does this:
codex exec -C /tmp/worker-1 "Label images using built-in vision..." &
codex exec -C /tmp/worker-2 "Label images using built-in vision..." &
codex exec -C /tmp/worker-3 "Label images using built-in vision..." &
codex exec -C /tmp/worker-4 "Label images using built-in vision..." &
```

---

### 3. API-Based Vision (Single-threaded)

```json
{
  "form_label_mode": "vision",
  "label_mode": "gemini"  // or "gpt" or "cua+sam"
}
```

**What it is:** Makes HTTP requests to OpenAI/Google APIs. No Cursor needed.

**Works on:**
- ✅ Your Mac
- ✅ Paperspace (with API keys in environment)
- ✅ Any server with internet

**Requires:**
- ✅ API keys (OPENAI_API_KEY or GEMINI_API_KEY)
- ❌ No Cursor needed
- ✅ Internet connection

**Speed:**
- Gemini: ⚡⚡ Fast (~1-2 sec/image)
- GPT: ⚡ Medium (~2-4 sec/image)
- CUA+SAM: 🐢 Slow (~10-20 sec/image, but best accuracy)

**Commands:**
```bash
# Gemini
uv run .agents/skills/label/scripts/label_gemini.py

# GPT-4V
uv run .agents/skills/label/scripts/run.py

# CUA+SAM (best accuracy)
uv run .agents/skills/label/scripts/label_cua_sam.py
```

---

## Comparison Table

| Mode | Needs Cursor? | Needs API Key? | Works on Paperspace? | Parallel? | Speed | Cost |
|------|---------------|----------------|----------------------|-----------|-------|------|
| **Programmatic** | ❌ No | ❌ No | ✅ Yes | N/A | ⚡⚡⚡ Instant | Free |
| **Codex agents** | ✅ Yes | ❌ No | ❌ No | ✅ 4x | ⚡⚡ Medium | Free |
| **Gemini API** | ❌ No | ✅ Yes | ✅ Yes | ❌ Single | ⚡⚡ Fast | ~$0.10 |
| **GPT API** | ❌ No | ✅ Yes | ✅ Yes | ❌ Single | ⚡ Medium | ~$0.50 |
| **CUA+SAM API** | ❌ No | ✅ Yes | ✅ Yes | ❌ Single | 🐢 Slow | ~$5.00 |

*Cost estimates for 100 images

---

## Why dispatch.sh Needs Cursor (Even with API Keys)

You might think: "If I use `label_mode: gpt` with an API key, shouldn't it work on Paperspace?"

**No, because dispatch.sh uses parallel Codex subagents:**

```bash
# Even in GPT mode, dispatch.sh spawns Codex subagents first
if [ "$LABEL_MODE" = "gpt" ]; then
    codex exec "Run: uv run .agents/skills/label/scripts/run_batch.py" &
    #     ↑
    #     This needs Cursor installed
fi
```

The subagents then call the GPT API, but you still need `codex exec` to spawn them.

---

## What Works Where

### On Your Mac (Cursor Installed)

**All modes work:**
- ✅ Programmatic
- ✅ Codex agents (parallel)
- ✅ Gemini API (with key)
- ✅ GPT API (with key)
- ✅ CUA+SAM (with key)

### On Paperspace (No Cursor)

**Only non-Codex modes work:**
- ✅ Programmatic
- ❌ Codex agents (no Cursor)
- ✅ Gemini API (with key)
- ✅ GPT API (with key)
- ✅ CUA+SAM (with key)

---

## Paperspace Workflows

### Option 1: All on Paperspace (No Cursor)

**Config:**
```json
{
  "form_label_mode": "vision",
  "label_mode": "gemini"  // or "gpt" or "cua+sam"
}
```

**Setup on Paperspace:**
```bash
# Add API key to environment
export GEMINI_API_KEY=your-key-here
# or add to .env file
echo "GEMINI_API_KEY=your-key-here" > .env
```

**Run:**
```bash
ssh paperspace@<your-ip> 'cd formdex && bash scripts/train_paperspace.sh'
```

**What happens:**
```
Paperspace:
  1. collect_form → Renders images (no labels)
  2. label_gemini.py → Makes API calls to Google
  3. augment → Augments data
  4. train → Trains on GPU
  5. eval → Evaluates
```

### Option 2: Label on Mac, Train on Paperspace

**Config:**
```json
{
  "form_label_mode": "vision",
  "label_mode": "codex",  // Use Codex on Mac
  "num_agents": 4
}
```

**Run:**
```bash
# Labels locally with Codex, trains remotely
bash scripts/train_paperspace_with_vision.sh paperspace@<your-ip>
```

**What happens:**
```
Your Mac:
  1. collect_form → Renders images
  2. dispatch.sh → 4 Codex subagents label in parallel
  3. augment → Augments data
  ↓ rsync upload ↓

Paperspace:
  4. train → Trains on GPU
  5. eval → Evaluates
  ↓ scp download ↓
  
Your Mac:
  best.pt (trained model)
```

---

## Summary

**"Agents" is ambiguous:**
- **Codex subagents** = Need Cursor (`codex exec`) = Only work on your Mac
- **API calls** = HTTP requests = Work anywhere with internet

**If you have API keys, you CAN run vision labeling on Paperspace** — just use the direct scripts (`label_gemini.py`, `run.py`, `label_cua_sam.py`), not `dispatch.sh`.

The updated `train_paperspace.sh` now supports this! Just set:
```json
{
  "form_label_mode": "vision",
  "label_mode": "gemini"  // Works on Paperspace with GEMINI_API_KEY
}
```

And make sure your API key is in `.env` on the Paperspace machine.

