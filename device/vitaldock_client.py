#!/usr/bin/env python3
"""Source-checkout entry; the installed training-system ships the same adapter."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).resolve().parents[1] / "skills" / "training-system" /
                       "scripts" / "vitaldock_client.py"), run_name="__main__")
