"""Construção segura de consultas para tabelas permitidas."""

import re
from typing import Any, Dict, Iterator, List, Optional, Tuple

from sqlalchemy import text, Engine
from sqlalchemy.sql.elements import TextClause


class QueryService:
    """Serviço para construção segura de consultas SQL com whitelist."""

    _SAFE_IDENTIFIER_RE = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')

    ALLOWED_COLUMNS: Dict[str, List[str]] = {
        "estabelecimentos": [
            "cnpj_basico", "cnpj_ordem", "cnpj_dv", "identificador_matriz_filial",
            "nome_fantasia", "situacao_cadastral", "data_situacao_cadastral",
            "motivo_situacao_cadastral", "nome_cidade_exterior", "pais",
            "data_inicio_atividade", "cnae_fiscal_principal", "cnae_fiscal_secundaria",
            "tipo_logradouro", "logradouro", "numero", "complemento", "bairro", "cep",
            "uf", "municipio", "codigo_municipio", "ddd_1", "telefone_1", "ddd_2", "telefone_2", "ddd_fax",
            "fax", "correio_eletronico", "situacao_especial", "data_situacao_especial",
            "operadora", "operadora_telefone", "categoria",
        ],
        "empresas": ["cnpj_basico", "razao_social", "natureza_juridica", "qualificacao_responsavel", "capital_social", "porte_empresa", "ente_federativo_responsavel"],
        "socios": ["cnpj_basico", "identificador_socio", "nome_socio", "cnpj_cpf_socio", "qualificacao_socio", "data_entrada_sociedade", "pais", "representante_legal", "nome_representante", "qualificacao_representante", "faixa_etaria"],
        "simples": ["cnpj_basico", "opcao_pelo_simples", "data_opcao_simples", "data_exclusao_simples", "opcao_pelo_mei", "data_opcao_mei", "data_exclusao_mei"],
        "cnaes": ["codigo", "descricao"],
        "municipios": ["codigo", "descricao"],
        "naturezas": ["codigo", "descricao"],
        "paises": ["codigo", "descricao"],
        "qualificacoes": ["codigo", "descricao"],
        "motivos": ["codigo", "descricao"],
    }

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def _validate_identifier(self, identifier: str) -> bool:
        """Valida se um identificador SQL é seguro."""
        return bool(self._SAFE_IDENTIFIER_RE.match(identifier))

    def build_select_query(
        self,
        table: str,
        columns: List[str],
        filters: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None
    ) -> Tuple[TextClause, Dict[str, Any]]:
        if table not in self.ALLOWED_COLUMNS:
            raise ValueError(f"Tabela nao permitida: {table}")
        if not columns:
            raise ValueError("Selecione ao menos uma coluna")
        allowed = set(self.ALLOWED_COLUMNS[table])
        invalid = [column for column in columns if column != "*" and column not in allowed]
        if invalid:
            raise ValueError(f"Colunas nao permitidas: {', '.join(invalid)}")
        
        # Validar identificadores dos filtros
        if filters:
            for field in filters.keys():
                if field != "*" and field not in allowed:
                    raise ValueError(f"Coluna de filtro nao permitida: {field}")

        params = {}
        clauses = []
        param_idx = 0
        for index, (field, value) in enumerate((filters or {}).items()):
            if field not in allowed or value in (None, "", []):
                continue
            if isinstance(value, list):
                names = []
                for item_index, item in enumerate(value):
                    name = f"filter_{index}_{item_index}"
                    names.append(f":{name}")
                    params[name] = item
                clauses.append(f"{field} IN ({', '.join(names)})")
            elif isinstance(value, str) and "%" in value:
                name = f"filter_{index}"
                clauses.append(f"{field} ILIKE :{name}")
                params[name] = value
            else:
                name = f"filter_{index}"
                clauses.append(f"{field} = :{name}")
                params[name] = value

        select_columns = "*" if columns == ["*"] else ", ".join(columns)
        sql = f"SELECT {select_columns} FROM {table}"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        if limit is not None:
            sql += " LIMIT :query_limit"
            params["query_limit"] = max(1, min(int(limit), 1_000_000))
        return text(sql), params

    def get_table_columns(self, table: str) -> List[str]:
        """Retorna colunas permitidas para uma tabela."""
        return self.ALLOWED_COLUMNS.get(table, [])

    def get_tables(self) -> List[str]:
        """Retorna lista de tabelas permitidas."""
        return list(self.ALLOWED_COLUMNS)

    def execute_query(self, table: str, columns: List[str], filters: Optional[Dict[str, Any]] = None, limit: int = 100_000, chunksize: int = 100_000) -> Iterator[Any]:
        """Executa query e retorna DataFrame."""
        import pandas as pd
        query, params = self.build_select_query(table, columns, filters, limit)
        return pd.read_sql(query, self.engine, params=params, chunksize=chunksize)

    def preview_data(self, table: str, columns: List[str], filters: Optional[Dict[str, Any]] = None, limit: int = 100) -> Dict[str, Any]:
        """Retorna preview dos dados."""
        import pandas as pd
        query, params = self.build_select_query(table, columns, filters, limit)
        df = pd.read_sql(query, self.engine, params=params)
        df = df.fillna("").astype(str)
        return {"columns": list(df.columns), "rows": df.values.tolist()}

    def count_records(self, table: str, filters: Optional[Dict[str, Any]] = None) -> int:
        """Conta registros de uma tabela."""
        if table not in self.ALLOWED_COLUMNS:
            raise ValueError(f"Tabela nao permitida: {table}")
        query, params = self.build_select_query(table, ["*"], filters)
        count_query = text(f"SELECT COUNT(*) FROM ({query.text}) AS selected_rows")
        with self.engine.connect() as connection:
            return int(connection.execute(count_query, params).scalar() or 0)
