import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)

MAX_BYTES = 10 * 1024 * 1024
BACKUP_COUNT = 7
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(module)-28s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

def get_logger(name: str, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT)
    log_file = LOGS_DIR / f"{name}.log"
    fh = RotatingFileHandler(log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8")
    fh.setFormatter(formatter)
    fh.setLevel(level)
    ch = logging.StreamHandler()
    ch.setFormatter(formatter)
    ch.setLevel(level)
    logger.addHandler(fh)
    logger.addHandler(ch)
    logger.propagate = False
    return logger

db_logger = get_logger("utils.db")
scheduler_logger = get_logger("scheduler.daily_tasks")
