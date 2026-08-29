"""Enables ``python -m input_recorder -d <dir> [options]``."""

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main(sys.argv))
