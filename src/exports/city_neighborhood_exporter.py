"""Exportacao filtrada por cidade e bairro."""

import re
import unicodedata
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Union

import pandas as pd
from sqlalchemy import text, Engine

from src.exports.csv_format import CSV_ENCODING, CSV_QUOTING, CSV_SEP, sanitize_text_columns
from src.services.business_rules_service import business_rules_service
from src.utils.env_loader import config
from src.utils.log_handler import logger

COLUNAS_EXPORT = [
    "cnpj_completo", "razao_social", "endereco_completo", "email", "cidade", "bairro",
    "uf", "cep", "telefone_1", "telefones", "operadora", "tipo_linha", "categoria",
    "data_inicio_atividade", "idade_cnpj",
]


def _safe_name(value: Any) -> str:
    normalized = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    normalized = re.sub(r"[^a-zA-Z0-9_-]+", "_", normalized.lower()).strip("_")
    return normalized or "sem_nome"


class CityNeighborhoodExporter:
    """Exporta registros agrupados por cidade ou bairro, preservando o legado."""

    def __init__(self, output_path: Optional[Union[str, Path]] = None, chunk_size: int = 100_000) -> None:
        self.output_path = Path(output_path or config.SILVER_DIR / "exports_discadora" / "por_cidade")
        self.cities_path = self.output_path / "cidades"
        self.neighborhoods_path = self.output_path / "bairros"
        self.cities_path.mkdir(parents=True, exist_ok=True)
        self.neighborhoods_path.mkdir(parents=True, exist_ok=True)
        self.chunk_size = chunk_size
        self._files_created = set()

    def _save(self, df: pd.DataFrame, path: Union[str, Path]) -> None:
        columns = [column for column in COLUNAS_EXPORT if column in df.columns]
        if df.empty or not columns:
            return
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        header = str(path) not in self._files_created
        with path.open("a", encoding=CSV_ENCODING, newline="") as stream:
            df[columns].to_csv(stream, index=False, sep=CSV_SEP, header=header, quoting=CSV_QUOTING)
        self._files_created.add(str(path))

    def _base_query(self) -> str:
        return """
            SELECT
                e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS cnpj_completo,
                COALESCE(emp.razao_social, e.nome_fantasia, '') AS razao_social,
                COALESCE(e.tipo_logradouro, '') || ' ' || COALESCE(e.logradouro, '') || ', ' ||
                    COALESCE(e.numero, '') || ', ' || COALESCE(e.complemento, '') || ', ' ||
                    COALESCE(e.bairro, '') || ', ' || COALESCE(e.uf, '') || ', ' || COALESCE(e.cep, '')
                    AS endereco_completo,
                e.correio_eletronico AS email,
                COALESCE(m.descricao, '') AS cidade,
                e.bairro, e.uf, e.cep, e.telefone_1,
                e.telefone_1 AS telefones,
                COALESCE(e.operadora, 'DESCONHECIDO') AS operadora,
                NULL::text AS tipo_linha,
                COALESCE(e.categoria, '') AS categoria,
                e.data_inicio_atividade,
                EXTRACT(YEAR FROM CURRENT_DATE)::int -
                    NULLIF(SUBSTRING(e.data_inicio_atividade FROM 1 FOR 4), '')::int AS idade_cnpj,
                emp.natureza_juridica, emp.porte_empresa AS porte,
                COALESCE(s.opcao_pelo_mei, 'N') AS opcao_mei
            FROM estabelecimentos e
            LEFT JOIN empresas emp ON e.cnpj_basico = emp.cnpj_basico
            LEFT JOIN simples s ON e.cnpj_basico = s.cnpj_basico
            LEFT JOIN municipios m ON e.municipio = m.codigo
            WHERE e.situacao_cadastral = '02'
              AND NULLIF(e.telefone_1, '') IS NOT NULL
        """

    def _read(self, filters: List[str], values: Dict[str, Any], engine: Engine) -> Iterator[pd.DataFrame]:
        clauses = [self._base_query()]
        for clause in filters:
            clauses.append(f" AND {clause}")
        query = text("".join(clauses))
        return pd.read_sql(query, engine, params=values, chunksize=self.chunk_size)

    def _prepare(self, chunk: pd.DataFrame) -> pd.DataFrame:
        chunk["endereco_completo"] = (
            chunk["endereco_completo"].fillna("").str.replace(r",\s*,", ",", regex=True)
            .str.replace(r"\s+", " ", regex=True).str.strip(" ,")
        )
        chunk["categoria"] = chunk.apply(
            lambda row: business_rules_service.categorize_empresa(
                natureza_juridica=row.get("natureza_juridica"),
                porte_empresa=row.get("porte"),
                opcao_mei=row.get("opcao_mei"),
            ), axis=1,
        )
        sanitize_text_columns(chunk)
        return chunk

    def export_by_city(self, engine: Engine, cidade: str, uf: Optional[str] = None, ano_inicial: Optional[int] = None) -> int:
        if not str(cidade).strip():
            raise ValueError("cidade deve ser informada")
        filters = ["m.descricao ILIKE :cidade"]
        values = {"cidade": f"%{cidade}%"}
        if uf:
            filters.append("e.uf = :uf")
            values["uf"] = uf.upper()
        if ano_inicial is not None:
            filters.append("SUBSTRING(e.data_inicio_atividade FROM 1 FOR 4)::int >= :ano_inicial")
            values["ano_inicial"] = int(ano_inicial)

        self._files_created.clear()
        total = 0
        for chunk in self._read(filters, values, engine):
            chunk = self._prepare(chunk)
            chunk["_year"] = chunk["data_inicio_atividade"].astype(str).str[:4]
            for (city, year), current in chunk.groupby(["cidade", "_year"], dropna=True):
                self._save(current, self.cities_path / year / f"cidade_{_safe_name(city)}.csv")
            total += len(chunk)
        logger.info("[CityNeighborhoodExporter] %s registros por cidade", f"{total:,}")
        return total

    def export_by_neighborhood(self, engine: Engine, bairro: str, cidade: Optional[str] = None, uf: Optional[str] = None) -> int:
        if not str(bairro).strip():
            raise ValueError("bairro deve ser informado")
        filters = ["e.bairro ILIKE :bairro"]
        values = {"bairro": f"%{bairro}%"}
        if cidade:
            filters.append("m.descricao ILIKE :cidade")
            values["cidade"] = f"%{cidade}%"
        if uf:
            filters.append("e.uf = :uf")
            values["uf"] = uf.upper()

        self._files_created.clear()
        total = 0
        for chunk in self._read(filters, values, engine):
            chunk = self._prepare(chunk)
            chunk["_year"] = chunk["data_inicio_atividade"].astype(str).str[:4]
            for (neighborhood, city, year), current in chunk.groupby(["bairro", "cidade", "_year"], dropna=True):
                filename = f"bairro_{_safe_name(neighborhood)}_{_safe_name(city)}.csv"
                self._save(current, self.neighborhoods_path / year / filename)
            total += len(chunk)
        logger.info("[CityNeighborhoodExporter] %s registros por bairro", f"{total:,}")
        return total

    def export_batch_cidades(self, engine: Engine, cidades: Iterable[str], uf: Optional[str] = None) -> int:
        return sum(self.export_by_city(engine, cidade, uf=uf) for cidade in cidades)


city_neighborhood_exporter = CityNeighborhoodExporter()
