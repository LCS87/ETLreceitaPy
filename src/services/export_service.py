"""Serviço de exportação de consultas em CSV."""

import re
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import Engine

from src.exports.csv_format import CSV_ENCODING, CSV_QUOTING, CSV_SEP, sanitize_text_columns
from src.utils.env_loader import config
from src.utils.log_handler import logger


class ExportService:
    """Serviço para exportação de dados em CSV."""

    def __init__(self, base_path: Optional[Path] = None) -> None:
        self.base_path = Path(base_path or config.SILVER_DIR / "exports")
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _validate_filename(self, filename: str) -> str:
        """Valida e sanitiza o nome do arquivo para evitar path traversal."""
        safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '_', filename)
        if not safe_name:
            raise ValueError("Nome de arquivo inválido")
        return safe_name

    def export_with_columns(self, engine: Engine, table: str, columns: list, filters: dict, filename: str, chunksize: int = 100_000) -> int:
        """Exporta dados de uma tabela para CSV."""
        from src.services.query_service import QueryService

        safe_filename = self._validate_filename(filename)
        path = self.base_path / f"{safe_filename}.csv"
        first = True
        total = 0
        service = QueryService(engine)
        for chunk in service.execute_query(table, columns, filters, chunksize=chunksize):
            if chunk.empty:
                continue
            sanitize_text_columns(chunk)
            with path.open("a" if not first else "w", encoding=CSV_ENCODING, newline="") as stream:
                chunk.to_csv(stream, index=False, sep=CSV_SEP, header=first, quoting=CSV_QUOTING)
            first = False
            total += len(chunk)
        logger.info("[ExportService] %s registros exportados para %s", f"{total:,}", path)
        return total

    def export_dataframe_to_csv(self, dataframe: pd.DataFrame, filename: str, append: bool = False) -> int:
        """Exporta DataFrame para CSV."""
        if dataframe.empty:
            return 0
        safe_filename = self._validate_filename(filename)
        path = self.base_path / f"{safe_filename}.csv"
        sanitize_text_columns(dataframe)
        with path.open("a" if append else "w", encoding=CSV_ENCODING, newline="") as stream:
            dataframe.to_csv(stream, index=False, sep=CSV_SEP, header=not append, quoting=CSV_QUOTING)
        return len(dataframe)

    def get_export_path(self, filename: str) -> Path:
        """Retorna o caminho completo para exportação."""
        safe_filename = self._validate_filename(filename)
        return self.base_path / f"{safe_filename}.csv"


export_service = ExportService()
