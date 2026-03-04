"""Centralized logging setup — file handler for the project."""

import datetime
import logging
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger with a daily log file in the logs/ folder."""
    root = logging.getLogger()
    root.setLevel(level)

    if any(isinstance(h, logging.FileHandler) for h in root.handlers):
        return

    LOG_DIR.mkdir(exist_ok=True)
    today = datetime.date.today().isoformat()
    log_file = LOG_DIR / f"{today}.log"

    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setLevel(level)
    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    root.addHandler(handler)
