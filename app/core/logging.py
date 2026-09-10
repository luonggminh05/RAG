import logging
import sys
from app.core.config import settings

_ENV_LOG_LEVELS = {
    "local": logging.DEBUG,
    "development": logging.DEBUG,
    "staging": logging.INFO,
    "production": logging.INFO,
}

_DEV_FORMAT = "%(levelname)-8s | %(asctime)s | %(location)s | %(message)s"
_PROD_FORMAT = "%(levelname)-8s | %(asctime)s | %(location)s | %(message)s"

_COLORS = {
    "DEBUG": "\033[36m",
    "INFO": "\033[32m",
    "WARNING": "\033[33m",
    "ERROR": "\033[31m",
    "CRITICAL": "\033[1;31m",
}
_RESET = "\033[0m"


class ColoredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        color = _COLORS.get(record.levelname, "")
        record.levelname = f"{color}{record.levelname:<8}{_RESET}"
        loc = f"{record.name}:{record.lineno}"
        record.location = f"{loc:<32}"
        return super().format(record)


class PlainFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        loc = f"{record.name}:{record.lineno}"
        record.location = f"{loc:<32}"
        return super().format(record)


def setup_logging(level: int | None = None, log_format: str | None = None) -> None:
    env = (getattr(settings, "ENVIRONMENT", "local") or "local").lower()
    if level is None:
        level = _ENV_LOG_LEVELS.get(env, logging.INFO)
    if log_format is None:
        log_format = _DEV_FORMAT if env in ("local", "development") else _PROD_FORMAT

    root = logging.getLogger()
    root.setLevel(level)

    for handler in root.handlers[:]:
        root.removeHandler(handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    if env in ("local", "development"):
        console_handler.setFormatter(ColoredFormatter(log_format, datefmt="%Y-%m-%d %H:%M:%S"))
    else:
        console_handler.setFormatter(PlainFormatter(log_format, datefmt="%Y-%m-%d %H:%M:%S"))

    root.addHandler(console_handler)

    # Suppress verbose loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
