"""Convenience entry point for terminal IDS runner."""
import sys
from pathlib import Path

# Add my_project to path and invoke run_terminal
project_path = Path(__file__).resolve().parent / "my_project"
if str(project_path) not in sys.path:
    sys.path.insert(0, str(project_path))

from run_terminal import main

if __name__ == "__main__":
    main()
