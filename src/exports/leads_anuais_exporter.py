"""Exportacao anual de leads do Nordeste entre 2010 e 2020."""

from pathlib import Path
from typing import Optional, Union

import pandas as pd
from sqlalchemy import create_engine, text, Engine, TextClause

from src.exports.csv_format import CSV_ENCODING, CSV_QUOTING, CSV_SEP, sanitize_text_columns
from src.services.business_rules_service import business_rules_service
from src.utils.env_loader import config
from src.utils.log_handler import logger

UFS = ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"]
COLUNAS = ["cnpj_completo", "razao_social", "endereco_completo", "email", "ano", "mes", "telefones", "operadora", "tipo_linha", "categoria"]


class LeadsAnuaisExporter:
    def __init__(self, output_path: Optional[Union[str, Path]] = None, chunk_size: int = 100_000) -> None:
        self.output_path = Path(output_path or config.SILVER_DIR / "exports_leads_anuais")
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.chunk_size = chunk_size
        self._created = set()

    def _query(self) -> TextClause:
        return text("""
            SELECT e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS cnpj_completo,
                   COALESCE(emp.razao_social, e.nome_fantasia, '') AS razao_social,
                   COALESCE(e.tipo_logradouro, '') || ' ' || COALESCE(e.logradouro, '') || ', ' || COALESCE(e.numero, '') || ', ' || COALESCE(e.bairro, '') || ', ' || COALESCE(e.uf, '') AS endereco_completo,
                   e.correio_eletronico AS email,
                   SUBSTRING(e.data_inicio_atividade FROM 1 FOR 4) AS ano,
                   SUBSTRING(e.data_inicio_atividade FROM 5 FOR 2) AS mes,
                   e.telefone_1 AS telefones,
                   COALESCE(e.operadora, 'DESCONHECIDO') AS operadora,
                   NULL::text AS tipo_linha,
                   e.categoria,
                   emp.natureza_juridica, emp.porte_empresa AS porte,
                   COALESCE(s.opcao_pelo_mei, 'N') AS opcao_mei, e.uf
            FROM estabelecimentos e
            LEFT JOIN empresas emp ON emp.cnpj_basico = e.cnpj_basico
            LEFT JOIN simples s ON s.cnpj_basico = e.cnpj_basico
            WHERE e.situacao_cadastral = '02' AND NULLIF(e.telefone_1, '') IS NOT NULL
              AND e.uf IN ('AL','BA','CE','MA','PB','PE','PI','RN','SE')
              AND SUBSTRING(e.data_inicio_atividade FROM 1 FOR 4) BETWEEN '2010' AND '2020'
        """)

    def _save(self, dataframe: pd.DataFrame, path: Path) -> None:
        columns = [column for column in COLUNAS if column in dataframe.columns]
        key = str(path)
        with path.open("a", encoding=CSV_ENCODING, newline="") as stream:
            dataframe[columns].to_csv(stream, index=False, sep=CSV_SEP, header=key not in self._created, quoting=CSV_QUOTING)
        self._created.add(key)

    def export(self, engine: Engine) -> int:
        self._created.clear()
        total = 0
        for chunk in pd.read_sql(self._query(), engine, chunksize=self.chunk_size):
            chunk["categoria"] = chunk.apply(lambda row: business_rules_service.categorize_empresa(row.get("natureza_juridica"), row.get("porte"), row.get("opcao_mei")), axis=1)
            sanitize_text_columns(chunk)
            for year, by_year in chunk.groupby("ano", dropna=True):
                for uf, current in by_year.groupby("uf", dropna=True):
                    path = self.output_path / str(year) / str(uf) / f"leads_{str(uf).lower()}.csv"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    self._save(current, path)
                path = self.output_path / str(year) / "NORDESTE" / "leads_nordeste.csv"
                path.parent.mkdir(parents=True, exist_ok=True)
                self._save(by_year, path)
            total += len(chunk)
        logger.info("[LeadsAnuais] %s registros exportados", f"{total:,}")
        return total

    def export_from_db(self, engine: Optional[Engine] = None) -> int:
        if engine is None:
            engine = create_engine(config.DATABASE_URL, pool_pre_ping=True)
        return self.export(engine)


leads_anuais_exporter = LeadsAnuaisExporter()
