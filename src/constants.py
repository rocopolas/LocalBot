"""Global constants for FemtoBot."""
import os


# Determine the absolute project root based on this file's location
_ABS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Set PROJECT_ROOT relative to the current working directory
PROJECT_ROOT = os.path.relpath(_ABS_ROOT, os.getcwd())
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
ASSETS_DIR = os.path.join(PROJECT_ROOT, "assets")
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
UTILS_DIR = os.path.join(PROJECT_ROOT, "utils")
