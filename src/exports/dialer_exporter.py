"""Compatibilidade do exportador de discadora com a nova regra temporal."""

from typing import Optional

from sqlalchemy import create_engine, Engine

from src.exports.time_based_exporter import TimeBasedExporter
from src.utils.env_loader import config


class DialerExporter(TimeBasedExporter):
    """Mantem a API antiga e delega a escrita ao exportador temporal."""

    def export_from_db(self, engine: Optional[Engine] = None) -> int:
        if engine is None:
            engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
        return super().export_from_db(engine)


dialer_exporter = DialerExporter()
