import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler


def setup_logger(name="elt_receita"):
    """
    Configura um logger centralizado com rotação de arquivos
    e saída formatada para o terminal.
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)

    # Evita duplicidade de logs se o logger já estiver configurado
    if logger.hasHandlers():
        return logger

    # Formato da mensagem: Data - Nome - Nível - Mensagem
    formatter = logging.Formatter(
        '%(asctime)s | %(name)s | %(levelname)s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # 1. Handler para o Console (Terminal)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # 2. Handler para Arquivo (com rotação para não encher o disco)
    log_dir = Path("docs/logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    file_handler = RotatingFileHandler(
        log_dir / "pipeline.log",
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


# Instância única para o projeto
logger = setup_logger()