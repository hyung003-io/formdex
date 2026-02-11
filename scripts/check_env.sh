#!/usr/bin/env bash
# Check environment setup for FormDex
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=== FormDex Environment Check ==="
echo ""

# Load .env if present
if [ -f "$REPO_ROOT/.env" ]; then
  echo "✅ .env file found"
  set -a
  source "$REPO_ROOT/.env"
  set +a
else
  echo "⚠️  No .env file found (optional)"
  echo "   Copy .env.example to .env if you want to use API-based labeling modes"
fi

echo ""
echo "--- Current Configuration ---"
if [ -f "$REPO_ROOT/config.json" ]; then
  python3 - <<'EOF'
import json
from pathlib import Path

config = json.loads(Path("config.json").read_text())
print(f"Project: {config.get('project', 'N/A')}")
print(f"Source type: {config.get('source_type', 'video')}")

if config.get('source_type') == 'form':
    print(f"Form label mode: {config.get('form_label_mode', 'programmatic')}")

print(f"Label mode: {config.get('label_mode', 'N/A')}")
print(f"Num agents: {config.get('num_agents', 'N/A')}")
EOF
else
  echo "❌ config.json not found"
fi

echo ""
echo "--- API Key Status ---"

# Check OpenAI
if [ -n "${OPENAI_API_KEY:-}" ]; then
  KEY_PREFIX=$(echo "$OPENAI_API_KEY" | cut -c1-10)
  echo "✅ OPENAI_API_KEY: ${KEY_PREFIX}... (set)"
  echo "   → Enables: label_mode=cua+sam, label_mode=gpt"
else
  echo "❌ OPENAI_API_KEY: not set"
  echo "   → label_mode=cua+sam and label_mode=gpt will fail"
fi

# Check Gemini
if [ -n "${GEMINI_API_KEY:-}" ] || [ -n "${GOOGLE_API_KEY:-}" ]; then
  if [ -n "${GEMINI_API_KEY:-}" ]; then
    KEY_PREFIX=$(echo "$GEMINI_API_KEY" | cut -c1-10)
    echo "✅ GEMINI_API_KEY: ${KEY_PREFIX}... (set)"
  else
    KEY_PREFIX=$(echo "$GOOGLE_API_KEY" | cut -c1-10)
    echo "✅ GOOGLE_API_KEY: ${KEY_PREFIX}... (set)"
  fi
  echo "   → Enables: label_mode=gemini"
else
  echo "❌ GEMINI_API_KEY/GOOGLE_API_KEY: not set"
  echo "   → label_mode=gemini will fail"
fi

# Check Anthropic (optional)
if [ -n "${ANTHROPIC_API_KEY:-}" ]; then
  KEY_PREFIX=$(echo "$ANTHROPIC_API_KEY" | cut -c1-10)
  echo "✅ ANTHROPIC_API_KEY: ${KEY_PREFIX}... (set)"
else
  echo "ℹ️  ANTHROPIC_API_KEY: not set (optional)"
fi

echo ""
echo "--- Mode Compatibility Check ---"

# Load config
if [ -f "$REPO_ROOT/config.json" ]; then
  LABEL_MODE=$(python3 -c "import json; print(json.load(open('config.json')).get('label_mode', 'N/A'))")
  SOURCE_TYPE=$(python3 -c "import json; print(json.load(open('config.json')).get('source_type', 'video'))")
  FORM_LABEL_MODE=$(python3 -c "import json; print(json.load(open('config.json')).get('form_label_mode', 'programmatic'))")

  if [ "$SOURCE_TYPE" = "form" ] && [ "$FORM_LABEL_MODE" = "programmatic" ]; then
    echo "✅ Mode: form (programmatic labeling)"
    echo "   → No API keys required! Uses PDF metadata."
    echo "   → Ready to run: bash formdex.sh"
  elif [ "$LABEL_MODE" = "codex" ]; then
    echo "✅ Mode: $LABEL_MODE"
    echo "   → No API keys required! Uses Codex built-in image viewing."
    echo "   → Ready to run: bash formdex.sh"
  elif [ "$LABEL_MODE" = "cua+sam" ] || [ "$LABEL_MODE" = "gpt" ]; then
    if [ -n "${OPENAI_API_KEY:-}" ]; then
      echo "✅ Mode: $LABEL_MODE"
      echo "   → OPENAI_API_KEY is set"
      echo "   → Ready to run: bash formdex.sh"
    else
      echo "❌ Mode: $LABEL_MODE"
      echo "   → OPENAI_API_KEY is REQUIRED but not set"
      echo "   → Add to .env file or export OPENAI_API_KEY=..."
    fi
  elif [ "$LABEL_MODE" = "gemini" ]; then
    if [ -n "${GEMINI_API_KEY:-}" ] || [ -n "${GOOGLE_API_KEY:-}" ]; then
      echo "✅ Mode: $LABEL_MODE"
      echo "   → GEMINI_API_KEY/GOOGLE_API_KEY is set"
      echo "   → Ready to run: bash formdex.sh"
    else
      echo "❌ Mode: $LABEL_MODE"
      echo "   → GEMINI_API_KEY or GOOGLE_API_KEY is REQUIRED but not set"
      echo "   → Add to .env file or export GEMINI_API_KEY=..."
    fi
  else
    echo "⚠️  Unknown label_mode: $LABEL_MODE"
  fi
fi

echo ""
echo "--- Required Tools ---"

# Check uv
if command -v uv >/dev/null 2>&1; then
  echo "✅ uv: $(uv --version 2>&1 | head -n1)"
else
  echo "❌ uv: not found"
  echo "   → Install: curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

# Check codex
if command -v codex >/dev/null 2>&1; then
  echo "✅ codex: found"
else
  echo "⚠️  codex: not found (optional, required for parallel subagents)"
fi

# Check ffmpeg
if command -v ffmpeg >/dev/null 2>&1; then
  echo "✅ ffmpeg: $(ffmpeg -version 2>&1 | head -n1 | cut -d' ' -f3)"
else
  echo "❌ ffmpeg: not found"
  echo "   → Install: brew install ffmpeg"
fi

# Check yt-dlp (only needed for video mode)
if [ "$SOURCE_TYPE" != "form" ]; then
  if command -v yt-dlp >/dev/null 2>&1; then
    echo "✅ yt-dlp: $(yt-dlp --version 2>&1)"
  else
    echo "❌ yt-dlp: not found (required for video mode)"
    echo "   → Install: brew install yt-dlp"
  fi
fi

echo ""
echo "=== Summary ==="

if [ -f "$REPO_ROOT/config.json" ]; then
  if [ "$SOURCE_TYPE" = "form" ] && [ "$FORM_LABEL_MODE" = "programmatic" ]; then
    echo "🎉 Your environment is ready!"
    echo "   Running: Form mode with programmatic labeling (no API keys needed)"
    echo "   Next: bash formdex.sh"
  elif [ "$LABEL_MODE" = "codex" ]; then
    echo "🎉 Your environment is ready!"
    echo "   Running: Codex vision mode (no API keys needed)"
    echo "   Next: bash formdex.sh"
  elif [ "$LABEL_MODE" = "cua+sam" ] || [ "$LABEL_MODE" = "gpt" ]; then
    if [ -n "${OPENAI_API_KEY:-}" ]; then
      echo "🎉 Your environment is ready!"
      echo "   Running: $LABEL_MODE mode with OPENAI_API_KEY"
      echo "   Next: bash formdex.sh"
    else
      echo "⚠️  Missing API key!"
      echo "   1. Copy .env.example to .env"
      echo "   2. Add your OPENAI_API_KEY"
      echo "   3. Re-run this script"
      echo ""
      echo "   Or switch to: label_mode=codex (no API key needed)"
    fi
  elif [ "$LABEL_MODE" = "gemini" ]; then
    if [ -n "${GEMINI_API_KEY:-}" ] || [ -n "${GOOGLE_API_KEY:-}" ]; then
      echo "🎉 Your environment is ready!"
      echo "   Running: gemini mode with GEMINI_API_KEY"
      echo "   Next: bash formdex.sh"
    else
      echo "⚠️  Missing API key!"
      echo "   1. Copy .env.example to .env"
      echo "   2. Add your GEMINI_API_KEY"
      echo "   3. Re-run this script"
      echo ""
      echo "   Or switch to: label_mode=codex (no API key needed)"
    fi
  fi
else
  echo "⚠️  config.json not found. Create it first."
fi

