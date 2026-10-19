"""Inicia a interface web de consulta e exportacao."""

import os

from src.api import run_interface
from src.utils.log_handler import logger


if __name__ == "__main__":
    port = int(os.getenv("WEB_INTERFACE_PORT", "5001"))
    logger.info("Interface web disponivel em http://localhost:%s", port)
    run_interface(port=port)
