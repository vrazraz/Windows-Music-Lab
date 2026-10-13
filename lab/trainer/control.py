"""Cooperative stop at the trainer's safe checkpoint boundary."""
import os
from pathlib import Path


def stop_requested(run_directory):
    configured = os.environ.get("RUACH_TRAIN_STOP_FILE")
    path = Path(configured) if configured else Path(run_directory) / "stop.requested"
    return path.is_file()
