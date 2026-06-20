import logging, os
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOGS_DIR = Path(__file__).parent.parent / "logs"
LOGS_DIR.mkdir(exist_ok=True)
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(module)-28s | %(message)s"

def get_logger(name, level=logging.INFO):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")
    fh = RotatingFileHandler(LOGS_DIR / f"{name}.log", maxBytes=10*1024*1024, backupCount=7, encoding="utf-8")
    fh.setFormatter(fmt); fh.setLevel(level)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt); ch.setLevel(level)
    logger.addHandler(fh); logger.addHandler(ch)
    logger.propagate = False
    return logger

db_logger = get_logger("utils.db")
scheduler_logger = get_logger("scheduler.daily_tasks")
