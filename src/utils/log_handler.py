"""
Handler de logs centralizado com suporte a JSON e rotação de arquivos.
"""

import logging
import sys
import json
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from typing import Any, Dict, Optional


class JSONFormatter(logging.Formatter):
    """Formatter para logs em formato JSON."""

    def format(self, record: logging.LogRecord) -> str:
        """Formata o registro como JSON."""
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Adicionar campos extras se existirem
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)

        # Adicionar exceção se existir
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, ensure_ascii=False)


def setup_logger(
    name: str = "elt_receita",
    log_level: Optional[str] = None,
    use_json: Optional[bool] = None,
) -> logging.Logger:
    """
    Configura um logger centralizado com rotação de arquivos.

    Args:
        name: Nome do logger
        log_level: Nível de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        use_json: Se True, usa formato JSON. Se None, usa variável de ambiente LOG_JSON

    Returns:
        Logger configurado
    """
    logger = logging.getLogger(name)

    # Determinar nível de log
    if log_level is None:
        log_level = "INFO"
    logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Evita duplicidade de logs se o logger já estiver configurado
    if logger.hasHandlers():
        return logger

    # Determinar formato (JSON ou texto)
    if use_json is None:
        use_json = False

    # Diretório de logs
    log_dir = Path("docs/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    # 1. Handler para o Console (Terminal)
    console_handler = logging.StreamHandler(sys.stdout)
    if use_json:
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
    logger.addHandler(console_handler)

    # 2. Handler para Arquivo JSON (com rotação)
    json_file_handler = RotatingFileHandler(
        log_dir / "pipeline.json.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    json_file_handler.setFormatter(JSONFormatter())
    logger.addHandler(json_file_handler)

    # 3. Handler para Arquivo Texto (com rotação)
    text_file_handler = RotatingFileHandler(
        log_dir / "pipeline.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding="utf-8",
    )
    text_file_handler.setFormatter(logging.Formatter(
        "%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    ))
    logger.addHandler(text_file_handler)

    return logger


def get_logger_with_context(**context) -> logging.LoggerAdapter:
    """
    Retorna um logger com contexto adicional.

    Uso:
        logger = get_logger_with_context(pipeline="receita", version="1.0")
        logger.info("Mensagem com contexto")
    """
    logger = logging.getLogger("elt_receita")
    return logging.LoggerAdapter(logger, context)


# Instância única para o projeto
logger = setup_logger()
