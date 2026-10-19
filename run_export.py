"""
Script para rodar APENAS a exportacao de leads do Nordeste.
Uso: py run_export.py

Exporta dados do periodo 2015-2022 sem alterar o codigo principal.
"""
import sys

if sys.platform == 'win32':
    import subprocess
    subprocess.run(['chcp', '65001'], shell=True, capture_output=True)

from src.utils.env_loader import config
from src.utils.log_handler import logger

# Intervalo de anos a exportar (configuravel aqui sem tocar no codigo principal)
ANO_INICIO_EXPORT = 2015
ANO_FIM_EXPORT = 2022

if __name__ == "__main__":
    logger.info(f"--- Iniciando exportacao standalone ({ANO_INICIO_EXPORT}-{ANO_FIM_EXPORT}) ---")
    config.validate()

    # Importa DEPOIS do validate para garantir que config esta pronta
    from src.exports.nordeste_exporter_optimized import NordesteExporterOptimized

    try:
        exporter = NordesteExporterOptimized(ano_inicio=ANO_INICIO_EXPORT, ano_fim=ANO_FIM_EXPORT)
        exporter.export_from_db()
        logger.info("--- Exportacao concluida com sucesso! ---")
    except Exception as e:
        logger.error(f"Erro na exportacao: {e}", exc_info=True)
        sys.exit(1)
