#!/bin/bash

# FemtoBot Universal Launcher
# Works on Linux, macOS, and Windows (Git Bash/WSL)

# Colors for output
GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

VENV_NAME="venv_bot"

# cd to the directory where this script lives
cd "$(dirname "$0")" || exit 1

echo -e "${CYAN}=== FemtoBot Universal Launcher ===${NC}"

# Detect OS
OS="unknown"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    OS="linux"
    PYTHON_CMD="python3"
elif [[ "$OSTYPE" == "darwin"* ]]; then
    OS="macos"
    PYTHON_CMD="python3"
elif [[ "$OSTYPE" == "cygwin" ]] || [[ "$OSTYPE" == "msys" ]] || [[ "$OSTYPE" == "win32" ]]; then
    OS="windows"
    PYTHON_CMD="python"
else
    echo -e "${YELLOW}Unknown OS, trying default settings...${NC}"
    PYTHON_CMD="python3"
fi

echo -e "${CYAN}Detected OS: $OS${NC}"

# Check Python version (3.11 required)
check_python() {
    # Prefer python3.11 explicitly, then check others
    for candidate in python3.11 python3 python; do
        if command -v "$candidate" &> /dev/null; then
            local version
            version=$($candidate -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null)
            if [ "$version" = "3.11" ]; then
                PYTHON_CMD="$candidate"
                return 0
            fi
        fi
    done
    return 1
}

if ! check_python; then
    echo -e "${RED}Python 3.11 is required but not found.${NC}"
    echo ""
    echo "Please install Python 3.11:"
    echo "  • Linux: sudo apt install python3.11 (or use your package manager)"
    echo "  • macOS: brew install python@3.11"
    echo "  • Windows: Download from https://python.org/downloads/"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

echo -e "${GREEN}✓ Python found: $($PYTHON_CMD --version 2>&1)${NC}"

# Check/create virtual environment
if [ "$OS" == "windows" ]; then
    VENV_ACTIVATE="$VENV_NAME/Scripts/activate"
else
    VENV_ACTIVATE="$VENV_NAME/bin/activate"
fi

if [ ! -f "$VENV_ACTIVATE" ]; then
    echo -e "${CYAN}Creating virtual environment...${NC}"
    $PYTHON_CMD -m venv "$VENV_NAME"

    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to create virtual environment${NC}"
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

# Activate virtual environment
echo -e "${CYAN}Activating virtual environment...${NC}"
source "$VENV_ACTIVATE"

# Always sync dependencies (pip skips already-installed packages)
if [ -f "requirements.txt" ]; then
    echo -e "${CYAN}Syncing dependencies...${NC}"
    pip install --upgrade pip --quiet 2>/dev/null
    pip install -r requirements.txt --quiet
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to install dependencies${NC}"
        read -p "Press Enter to exit..."
        exit 1
    fi
    echo -e "${GREEN}✓ Dependencies ready${NC}"
else
    echo -e "${RED}requirements.txt not found${NC}"
    read -p "Press Enter to exit..."
    exit 1
fi

# Check if Ollama is running
if command -v curl &> /dev/null; then
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${YELLOW}⚠ Ollama no está corriendo. Ejecutá 'ollama serve' en otra terminal.${NC}"
    else
        echo -e "${GREEN}✓ Ollama detectado${NC}"
    fi
fi

echo ""
echo -e "${GREEN}🚀 Starting FemtoBot...${NC}"
echo ""

# Run the bot
python src/telegram_bot.py

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    read -p "Press Enter to exit..."
fi

exit $EXIT_CODE
