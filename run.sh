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

# Check Python version
check_python() {
    if command -v python3.12 &> /dev/null; then
        PYTHON_CMD="python3.12"
        return 0
    elif command -v python3 &> /dev/null; then
        # Check if version is 3.11+
        PY_VERSION=$($PYTHON_CMD --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
        MAJOR=$(echo $PY_VERSION | cut -d. -f1)
        MINOR=$(echo $PY_VERSION | cut -d. -f2)
        
        if [ "$MAJOR" -eq 3 ] && [ "$MINOR" -ge 11 ]; then
            return 0
        fi
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
        return 0
    fi
    return 1
}

if ! check_python; then
    echo -e "${RED}Python 3.11+ is required but not found.${NC}"
    echo ""
    echo "Please install Python 3.11 or higher:"
    echo "  • Linux: sudo apt install python3.12 (or use your package manager)"
    echo "  • macOS: brew install python@3.12"
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

# Check dependencies
if ! python -c "import telegram; import chromadb" 2>/dev/null; then
    echo -e "${YELLOW}Installing dependencies...${NC}"
    
    pip install --upgrade pip --quiet
    
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

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    read -p "Press Enter to exit..."
fi

exit $EXIT_CODE
