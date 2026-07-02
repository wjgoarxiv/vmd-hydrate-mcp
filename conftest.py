"""Make the src-layout package importable without an editable install."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
