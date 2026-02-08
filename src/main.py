import os
import sys

# Add parent directory to path for imports
_ABS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ABS_ROOT)

from src.tui import FemtoBotApp

def main():
    app = FemtoBotApp()
    app.run()

if __name__ == "__main__":
    main()
