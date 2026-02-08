#!/bin/bash

# FemtoBot macOS Launcher
# This script sets up and runs FemtoBot on macOS

# Colors for output
GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

VENV_NAME="venv_bot"
PYTHON_CMD="python3"

echo -e "${CYAN}=== FemtoBot - macOS Setup ===${NC}"

# Check if Python 3.12+ is available
check_python() {
    if command -v python3.12 &> /dev/null; then
        PYTHON_CMD="python3.12"
        return 0
    elif command -v python3 &> /dev/null; then
        # Check version
        PY_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
        if (( $(echo "$PY_VERSION >= 3.12" | bc -l) )); then
            return 0
        fi
    fi
    return 1
}

if ! check_python; then
    echo -e "${RED}Python 3.12+ is required but not found.${NC}"
    echo ""
    echo "Please install Python 3.12 using one of these methods:"
    echo "  • Homebrew: brew install python@3.12"
    echo "  • pyenv: pyenv install 3.12.0"
    echo "  • Official installer: https://www.python.org/downloads/macos/"
    echo ""
    read -p "Press Enter to exit..."
    exit 1
fi

echo -e "${GREEN}✓ Python found: $($PYTHON_CMD --version)${NC}"

# Check if virtual environment exists
if [ ! -d "$VENV_NAME" ] || [ ! -f "$VENV_NAME/bin/activate" ]; then
    echo -e "${CYAN}Creating virtual environment...${NC}"
    $PYTHON_CMD -m venv "$VENV_NAME"
    
    if [ $? -ne 0 ]; then
        echo -e "${RED}Failed to create virtual environment${NC}"
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

echo -e "${GREEN}✓ Virtual environment ready${NC}"

# Activate virtual environment
source "$VENV_NAME/bin/activate"

# Check if dependencies are installed
if ! $PYTHON_CMD -c "import telegram" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    
    # Upgrade pip
    pip install --upgrade pip --quiet
    
    # Install requirements
    if [ -f "requirements.txt" ]; then
        pip install -r requirements.txt
        if [ $? -ne 0 ]; then
            echo -e "${RED}Failed to install dependencies${NC}"
            read -p "Press Enter to exit..."
            exit 1
        fi
    else
        echo -e "${RED}requirements.txt not found${NC}"
        read -p "Press Enter to exit..."
        exit 1
    fi
    
    echo -e "${GREEN}✓ Dependencies installed!${NC}"
else
    echo -e "${GREEN}✓ Dependencies already installed${NC}"
fi

echo ""
echo -e "${GREEN}🚀 Starting FemtoBot...${NC}"
echo ""

# Run the bot
python src/telegram_bot.py

# Keep terminal open if there's an error
if [ $? -ne 0 ]; then
    echo ""
    read -p "Press Enter to exit..."
fi
