"""Headless logging helpers retained for donor-compatible backend modules."""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

log_dir = os.path.abspath(os.environ.get(
    "EASY_CIDAREN_LOG_DIR",
    os.path.join(os.path.dirname(__file__), "logs"),
))
os.makedirs(log_dir, exist_ok=True)
log_filename = os.path.join(log_dir, "backend.log")


def _file_handler() -> RotatingFileHandler:
    handler = RotatingFileHandler(
        log_filename, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "[%(asctime)s] %(name)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    return handler


def setup_logger() -> logging.Logger:
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(_file_handler())
        logger.addHandler(logging.StreamHandler())
    return logger


def get_file_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    if not logger.handlers:
        logger.addHandler(_file_handler())
        logger.propagate = False
    return logger


logger_instance = setup_logger()


class Log:
    def __init__(self, logger_name: str):
        self.logger = logging.getLogger(logger_name)

    def info(self, message, *args, **kwargs):
        self.logger.info(message, *args, **kwargs)

    def error(self, message, *args, **kwargs):
        self.logger.error(message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        self.logger.warning(message, *args, **kwargs)

    def debug(self, message, *args, **kwargs):
        self.logger.debug(message, *args, **kwargs)
