#!/bin/bash
# Installs 'femtobot' command system-wide
# Creates a wrapper in /usr/local/bin that calls the venv directly

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv_bot/bin/python"
CLI_MODULE="src.cli"
TARGET="/usr/local/bin/femtobot"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "❌ venv_bot not found. Run './run.sh' first to set up the environment."
    exit 1
fi

# Ensure femtobot is installed in the venv
"$VENV_PYTHON" -m pip install -e "$SCRIPT_DIR" --quiet 2>/dev/null

echo "Creating $TARGET ..."

sudo tee "$TARGET" > /dev/null << EOF
#!/bin/bash
exec "$VENV_PYTHON" -m src.cli "\$@"
EOF

sudo chmod +x "$TARGET"

echo "✅ Done! 'femtobot' is now available system-wide."
echo "   Try: femtobot --help"
