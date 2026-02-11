#!/usr/bin/env bash
# Helper script to create or fix .env file
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$REPO_ROOT/.env"

echo "=== FormDex .env Setup ==="
echo ""

# Check if .env exists
if [ -f "$ENV_FILE" ]; then
  echo "Found existing .env file"
  echo ""
  
  # Try to source it and check for errors
  if bash -n "$ENV_FILE" 2>/dev/null; then
    echo "✅ .env syntax is valid"
  else
    echo "❌ .env has syntax errors"
    echo ""
    echo "Would you like to:"
    echo "1. Backup and recreate .env (creates .env.backup)"
    echo "2. Open .env in editor to fix manually"
    echo "3. Cancel"
    read -p "Choice (1/2/3): " choice
    
    case $choice in
      1)
        mv "$ENV_FILE" "$ENV_FILE.backup"
        echo "✅ Backed up to .env.backup"
        echo "Creating new .env..."
        ;;
      2)
        ${EDITOR:-nano} "$ENV_FILE"
        echo ""
        echo "✅ Done editing. Run 'bash scripts/check_env.sh' to verify."
        exit 0
        ;;
      3)
        echo "Cancelled."
        exit 0
        ;;
    esac
  fi
else
  echo "No .env file found. Creating one..."
fi

# Create .env template
cat > "$ENV_FILE" << 'EOF'
# FormDex Environment Variables
# 
# IMPORTANT: You DON'T need these for Codex or Programmatic modes!
# Only fill these out if you want to use CUA+SAM, Gemini, or GPT modes.

# ==============================================================================
# OpenAI API Key (for CUA+SAM and GPT vision modes)
# ==============================================================================
# Get yours at: https://platform.openai.com/api-keys
# Uncomment and add your key below:
# OPENAI_API_KEY=sk-proj-your-key-here

# ==============================================================================
# Google Gemini API Key (for Gemini vision mode)
# ==============================================================================
# Get yours at: https://aistudio.google.com/app/apikey
# Uncomment and add your key below:
# GEMINI_API_KEY=your-gemini-key-here
# OR use GOOGLE_API_KEY instead:
# GOOGLE_API_KEY=your-google-key-here

# ==============================================================================
# Current Setup
# ==============================================================================
# Your config.json is set to:
#   - label_mode: codex
#   - form_label_mode: vision
# 
# This means you DON'T need any API keys! Codex uses built-in image viewing.
# You're ready to run: bash formdex.sh
EOF

echo ""
echo "✅ Created .env with template"
echo ""
echo "📝 What's next?"
echo ""
echo "Option 1 (Recommended): Use Codex mode — no API keys needed"
echo "  → Just run: bash formdex.sh"
echo "  → Your current config is already set for this!"
echo ""
echo "Option 2: Add API keys to try other modes"
echo "  1. Edit .env: nano .env"
echo "  2. Uncomment and add your API keys"
echo "  3. Save and run: bash scripts/check_env.sh"
echo ""
echo "Option 3: Try programmatic mode — even faster, still free"
echo "  1. Edit config.json: change form_label_mode to 'programmatic'"
echo "  2. Run: bash formdex.sh"
echo ""

read -p "Would you like to open .env in editor now? (y/N): " edit_now

if [[ "$edit_now" =~ ^[Yy] ]]; then
  ${EDITOR:-nano} "$ENV_FILE"
  echo ""
  echo "✅ Done editing. Run 'bash scripts/check_env.sh' to verify."
else
  echo ""
  echo "✅ Setup complete! Run 'bash scripts/check_env.sh' when ready."
fi

