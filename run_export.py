"""
Script para rodar APENAS a exportacao de leads do Nordeste.
Uso: py run_export.py
"""
import sys

if sys.platform == 'win32':
    import subprocess
    subprocess.run(['chcp', '65001'], shell=True, capture_output=True)

from src.utils.env_loader import config
from src.utils.log_handler import logger

if __name__ == "__main__":
    logger.info("--- Iniciando exportacao standalone ---")
    config.validate()

    # Importa DEPOIS do validate para garantir que config esta pronta
    from src.exports.nordeste_exporter_optimized import NordesteExporterOptimized

    try:
        exporter = NordesteExporterOptimized()
        exporter.export_from_db()
        logger.info("--- Exportacao concluida com sucesso! ---")
    except Exception as e:
        logger.error(f"Erro na exportacao: {e}", exc_info=True)
        sys.exit(1)
