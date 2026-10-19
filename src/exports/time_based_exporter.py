"""Exportacao de leads por ano, trimestre, mes e decada."""

from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd
from sqlalchemy import text, Engine, TextClause

from src.exports.csv_format import CSV_ENCODING, CSV_QUOTING, CSV_SEP, sanitize_text_columns
from src.exports.period_utils import ano_em_detalhe, nome_decada
from src.services.business_rules_service import business_rules_service
from src.utils.env_loader import config
from src.utils.log_handler import logger

NORDESTE_UFS = ["AL", "BA", "CE", "MA", "PB", "PE", "PI", "RN", "SE"]
COLUNAS_EXPORT = [
    "cnpj_completo", "nome_fantasia", "razao_social", "categoria_porte",
    "cnae_principal_desc", "cnae_secundario_desc", "telefones",
    "tipo_linha", "operadora", "email_validado", "endereco_formatado",
    "cidade", "uf", "idade_cnpj_anos", "lead_score", "fonte_consulta_operadora",
]


class TimeBasedExporter:
    """Exporta dados do banco sem carregar o resultado completo em memoria."""

    def __init__(self, output_path: Optional[Union[str, Path]] = None, chunk_size: int = 100_000) -> None:
        self.output_path = Path(output_path or config.SILVER_DIR / "exports_discadora")
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.chunk_size = chunk_size
        self._files_created = set()

    def _period_path(self, kind: str, value: Any, uf: str) -> Path:
        path = self.output_path / kind / str(value) / uf
        path.mkdir(parents=True, exist_ok=True)
        return path / f"leads_{uf.lower()}.csv"

    def _save(self, df: pd.DataFrame, path: Union[str, Path]) -> None:
        if df.empty:
            return
        path = Path(path)
        header = str(path) not in self._files_created
        with path.open("a", encoding=CSV_ENCODING, newline="") as stream:
            df.to_csv(stream, index=False, sep=CSV_SEP, header=header, quoting=CSV_QUOTING)
        self._files_created.add(str(path))

    def _get_trimester(self, month: Any) -> Optional[str]:
        month = int(month)
        if not 1 <= month <= 12:
            return None
        return f"Q{((month - 1) // 3) + 1}"

    def _export_dataframe(self, df: pd.DataFrame, uf: str) -> None:
        columns = [column for column in COLUNAS_EXPORT if column in df.columns]
        if not columns:
            return
        detail_mask = df["ano"].apply(ano_em_detalhe)
        detail = df[detail_mask]
        decades = df[~detail_mask].copy()

        for year in detail["ano"].dropna().unique():
            current = detail[detail["ano"] == year]
            self._save(current[columns], self._period_path("anual", year, uf))
            current = current.copy()
            current["trimestre"] = current["mes"].apply(self._get_trimester)
            for trimester in current["trimestre"].dropna().unique():
                period = current[current["trimestre"] == trimester]
                self._save(period[columns], self._period_path("trimestral", f"{year}_{trimester}", uf))
            for (period_year, month), period in current.groupby(["ano", "mes"]):
                if pd.isna(period_year) or pd.isna(month):
                    continue
                self._save(period[columns], self._period_path("mensal", f"{period_year}_{int(month):02d}", uf))

        if not decades.empty:
            decades["decada"] = decades["ano"].apply(nome_decada)
            for decade, period in decades.groupby("decada", dropna=True):
                self._save(period[columns], self._period_path("decada", decade, uf))

    def _query(self) -> TextClause:
        return text("""
            SELECT
                e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv AS cnpj_completo,
                COALESCE(emp.razao_social, e.nome_fantasia, '') AS razao_social,
                COALESCE(e.tipo_logradouro, '') || ' ' || COALESCE(e.logradouro, '') || ', ' ||
                    COALESCE(e.numero, '') || ', ' || COALESCE(e.complemento, '') || ', ' ||
                    COALESCE(e.bairro, '') || ', ' || COALESCE(e.uf, '') || ', ' || COALESCE(e.cep, '')
                    AS endereco_completo,
                e.correio_eletronico AS email,
                SUBSTRING(e.data_inicio_atividade FROM 1 FOR 4) AS ano,
                SUBSTRING(e.data_inicio_atividade FROM 5 FOR 2)::int AS mes,
                COALESCE(e.ddd_1, '') || COALESCE(e.telefone_1, '') AS telefones,
                COALESCE(NULLIF(e.operadora, ''), 'DESCONHECIDO') AS operadora,
                CASE WHEN LENGTH(COALESCE(e.telefone_1, '')) <= 8 THEN 'FIXO' ELSE 'MOVEL' END AS tipo_linha,
                'RECEITA'::text AS fonte_consulta_operadora,
                COALESCE(NULLIF(e.categoria, ''), '') AS categoria,
                e.cnae_fiscal_principal AS cnae_principal,
                COALESCE(cnae.descricao, 'ATIVIDADE NÃO MAPEADA') AS cnae_principal_desc,
                SPLIT_PART(COALESCE(e.cnae_fiscal_secundaria, ''), ',', 1) AS cnae_secundario,
                NULL::text AS cnae_secundario_desc,
                EXTRACT(YEAR FROM CURRENT_DATE)::int -
                    NULLIF(SUBSTRING(e.data_inicio_atividade FROM 1 FOR 4), '')::int AS idade_cnpj,
                emp.natureza_juridica,
                emp.porte_empresa AS porte,
                COALESCE(NULLIF(s.opcao_pelo_mei, ''), 'N') AS opcao_mei,
                e.uf
            FROM estabelecimentos e
            LEFT JOIN empresas emp ON e.cnpj_basico = emp.cnpj_basico
            LEFT JOIN simples s ON e.cnpj_basico = s.cnpj_basico
            LEFT JOIN cnaes cnae ON e.cnae_fiscal_principal = cnae.codigo
            WHERE e.situacao_cadastral = '02'
              AND NULLIF(e.telefone_1, '') IS NOT NULL
              AND e.uf IN ('AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE')
              AND e.data_inicio_atividade ~ '^[0-9]{8}$'
        """)

    def export_from_db(self, engine: Engine) -> int:
        """Executa a exportacao por periodos usando leitura em chunks."""
        self._files_created.clear()
        total = 0
        for chunk in pd.read_sql(self._query(), engine, chunksize=self.chunk_size):
            if chunk.empty:
                continue
            chunk["endereco_completo"] = (
                chunk["endereco_completo"].fillna("").str.replace(r",\s*,", ",", regex=True)
                .str.replace(r"\s+", " ", regex=True).str.strip(" ,")
            )
            # Formatação de telefone e limpeza de razão social
            chunk["telefones"] = chunk["telefones"].apply(
                lambda x: f"({str(x)[-10:-8]}) {str(x)[-8:-4]}-{str(x)[-4:]}" if pd.notna(x) and len(str(x)) >= 10 else str(x)
            )
            chunk["razao_social"] = chunk["razao_social"].str.replace(r"^\d+\.\d+\.\d+\s+", "", regex=True)
            sanitize_text_columns(chunk)
            for uf in NORDESTE_UFS:
                current = chunk[chunk["uf"] == uf]
                if not current.empty:
                    self._export_dataframe(current, uf)
            total += len(chunk)
        logger.info("[TimeBasedExporter] %s registros exportados", f"{total:,}")
        return total


time_based_exporter = TimeBasedExporter()
