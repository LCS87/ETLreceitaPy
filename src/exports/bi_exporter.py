"""Exportacao agregada para BI por UF e periodo."""

from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd
from sqlalchemy import create_engine, text, Engine, TextClause

from src.exports.csv_format import CSV_ENCODING, CSV_QUOTING, CSV_SEP, sanitize_text_columns
from src.utils.env_loader import config
from src.utils.log_handler import logger

UFS = ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"]


class BIExporter:
    def __init__(self, output_path: Optional[Union[str, Path]] = None, chunk_size: int = 100_000) -> None:
        self.output_path = Path(output_path or config.SILVER_DIR / "exports_bi")
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.chunk_size = chunk_size
        self._created = set()

    def _query(self) -> TextClause:
        return text("""
            SELECT e.uf, SUBSTRING(e.data_inicio_atividade FROM 1 FOR 4) AS ano,
                   SUBSTRING(e.data_inicio_atividade FROM 5 FOR 2)::int AS mes,
                   COALESCE(e.operadora, 'DESCONHECIDO') AS operadora, e.cnae_fiscal_principal AS cnae_principal,
                   emp.natureza_juridica, emp.porte_empresa AS porte, COALESCE(s.opcao_pelo_mei, 'N') AS opcao_mei,
                   COUNT(*) AS total_leads
            FROM estabelecimentos e
            LEFT JOIN empresas emp ON emp.cnpj_basico = e.cnpj_basico
            LEFT JOIN simples s ON s.cnpj_basico = e.cnpj_basico
            WHERE e.situacao_cadastral = '02' AND NULLIF(e.telefone_1, '') IS NOT NULL
              AND e.uf IN ('AL','BA','CE','MA','PB','PE','PI','RN','SE')
            GROUP BY e.uf, ano, mes, COALESCE(e.operadora, 'DESCONHECIDO'), e.cnae_fiscal_principal, emp.natureza_juridica, emp.porte_empresa, s.opcao_pelo_mei
        """)

    def _save(self, dataframe: pd.DataFrame, kind: str, period: Any, uf: str) -> None:
        path = self.output_path / kind / str(period) / uf / f"resumo_bi_{uf.lower()}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        key = str(path)
        with path.open("a", encoding=CSV_ENCODING, newline="") as stream:
            dataframe.to_csv(stream, index=False, sep=CSV_SEP, header=key not in self._created, quoting=CSV_QUOTING)
        self._created.add(key)

    def export_summary(self, engine: Engine) -> int:
        self._created.clear()
        total = 0
        for chunk in pd.read_sql(self._query(), engine, chunksize=self.chunk_size):
            chunk["categoria"] = chunk.apply(lambda row: "MEI" if str(row.get("natureza_juridica")) == "2135" and str(row.get("opcao_mei")) == "S" else "ME" if str(row.get("porte")) == "01" else "LTDA" if str(row.get("natureza_juridica")) == "2062" else "OUTRA", axis=1)
            sanitize_text_columns(chunk)
            for uf, current in chunk.groupby("uf", dropna=True):
                current = current.drop(columns=["uf", "natureza_juridica", "porte", "opcao_mei"])
                current["trimestre"] = current["mes"].apply(lambda month: f"Q{((int(month) - 1) // 3) + 1}" if int(month) else "")
                for year, period in current.groupby("ano", dropna=True):
                    self._save(period.drop(columns=["trimestre"]), "anual", year, uf)
                for (year, quarter), period in current.groupby(["ano", "trimestre"], dropna=True):
                    self._save(period.drop(columns=["trimestre"]), "trimestral", f"{year}_{quarter}", uf)
                for (year, month), period in current.groupby(["ano", "mes"], dropna=True):
                    self._save(period.drop(columns=["trimestre"]), "mensal", f"{year}_{int(month):02d}", uf)
            total += len(chunk)
        logger.info("[BIExporter] %s grupos exportados", f"{total:,}")
        return total

    def export_from_db(self, engine: Optional[Engine] = None) -> int:
        if engine is None:
            engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
        return self.export_summary(engine)


bi_exporter = BIExporter()
