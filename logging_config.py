"""Configuración de logging — formato JSON para que Railway/Sentry/Loki/etc.
parseen los campos sin tener que regex el mensaje.
"""
import json
import logging
import os
import sys
from typing import Optional


_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
}


class JsonFormatter(logging.Formatter):
    """Un log por línea, JSON. Campos extra via logger.info("x", extra={...})."""

    def format(self, record: logging.LogRecord) -> str:
        data = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)
        for k, v in record.__dict__.items():
            if k in _RESERVED or k.startswith("_"):
                continue
            try:
                json.dumps(v)
                data[k] = v
            except TypeError:
                data[k] = repr(v)
        return json.dumps(data, ensure_ascii=False)


def setup_logging(level: Optional[str] = None) -> None:
    """Configura el root logger. Idempotente."""
    level = (level or os.getenv("LOG_LEVEL", "INFO")).upper()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    # Reemplazar handlers existentes (uvicorn agrega los suyos por defecto)
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    # Silenciar loggers ruidosos de libs comunes
    logging.getLogger("urllib3").setLevel("WARNING")
    logging.getLogger("httpx").setLevel("WARNING")
    logging.getLogger("playwright").setLevel("WARNING")
