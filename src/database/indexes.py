"""
Definições centralizadas de índices do banco de dados.
Remove duplicação de código e facilita manutenção.
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class IndexDefinition:
    """Definição de um índice do banco de dados."""
    name: str
    table: str
    columns: List[str]
    unique: bool = False
    if_not_exists: bool = True
    using: Optional[str] = None       # ex: "GIN", "BTREE"
    column_ops: Optional[str] = None  # ex: "gin_trgm_ops" (aplica em cada coluna)
    where: Optional[str] = None       # índice parcial


# Extensões necessárias antes de criar índices especiais
REQUIRED_EXTENSIONS = [
    "CREATE EXTENSION IF NOT EXISTS pg_trgm;",
]

# Índices de otimização para performance de consultas
OPTIMIZATION_INDEXES = [
    # Estabelecimentos
    IndexDefinition(
        name="idx_establ_uf",
        table="estabelecimentos",
        columns=["uf"]
    ),
    IndexDefinition(
        name="idx_establ_cnpj",
        table="estabelecimentos",
        columns=["cnpj_basico", "cnpj_ordem", "cnpj_dv"]
    ),
    IndexDefinition(
        name="idx_establ_municipio",
        table="estabelecimentos",
        columns=["municipio"]
    ),
    IndexDefinition(
        name="idx_establ_situacao",
        table="estabelecimentos",
        columns=["situacao_cadastral"]
    ),
    IndexDefinition(
        name="idx_establ_operadora",
        table="estabelecimentos",
        columns=["operadora"]
    ),
    IndexDefinition(
        name="idx_establ_categoria",
        table="estabelecimentos",
        columns=["categoria"]
    ),
    IndexDefinition(
        name="idx_establ_cnae",
        table="estabelecimentos",
        columns=["cnae_fiscal_principal"]
    ),
    # Índice composto parcial: filtro mais frequente (ativos + UF)
    IndexDefinition(
        name="idx_establ_uf_ativo",
        table="estabelecimentos",
        columns=["uf", "municipio"],
        where="situacao_cadastral = '02'",
    ),
    # Trigramas GIN — aceleram ILIKE '%texto%' em bairro
    IndexDefinition(
        name="idx_establ_bairro_trgm",
        table="estabelecimentos",
        columns=["bairro"],
        using="GIN",
        column_ops="gin_trgm_ops",
    ),

    # Leads Nordeste (se existir)
    IndexDefinition(
        name="idx_leads_uf",
        table="leads_nordeste",
        columns=["uf"]
    ),
    IndexDefinition(
        name="idx_leads_categoria",
        table="leads_nordeste",
        columns=["categoria"]
    ),
    IndexDefinition(
        name="idx_leads_operadora",
        table="leads_nordeste",
        columns=["operadora"]
    ),

    # Empresas
    IndexDefinition(
        name="idx_empresas_cnpj",
        table="empresas",
        columns=["cnpj_basico"]
    ),
    IndexDefinition(
        name="idx_empresas_natureza",
        table="empresas",
        columns=["natureza_juridica"]
    ),
    IndexDefinition(
        name="idx_empresas_porte",
        table="empresas",
        columns=["porte_empresa"]
    ),

    # Socios
    IndexDefinition(
        name="idx_socios_cnpj",
        table="socios",
        columns=["cnpj_basico"]
    ),
    IndexDefinition(
        name="idx_socios_cpf",
        table="socios",
        columns=["cpf_socio"]
    ),

    # Cnaes
    IndexDefinition(
        name="idx_cnae_codigo",
        table="cnaes",
        columns=["codigo"]
    ),

    # Motivos Situação Cadastral
    IndexDefinition(
        name="idx_motivos_codigo",
        table="motivos_situacao_cadastral",
        columns=["codigo"]
    ),

    # Naturezas Jurídicas
    IndexDefinition(
        name="idx_naturezas_codigo",
        table="naturezas_juridicas",
        columns=["codigo_natureza"]
    ),

    # Municípios
    IndexDefinition(
        name="idx_municipios_codigo",
        table="municipios",
        columns=["codigo"]
    ),
    IndexDefinition(
        name="idx_municipios_uf",
        table="municipios",
        columns=["uf"]
    ),
    # Trigramas GIN — aceleram ILIKE '%texto%' em descrição de município
    IndexDefinition(
        name="idx_municipios_descricao_trgm",
        table="municipios",
        columns=["descricao"],
        using="GIN",
        column_ops="gin_trgm_ops",
    ),

    # Países
    IndexDefinition(
        name="idx_paises_codigo",
        table="paises",
        columns=["codigo"]
    ),

    # Qualificações
    IndexDefinition(
        name="idx_qualificacoes_codigo",
        table="qualificacoes",
        columns=["codigo"]
    ),
]

# Índices únicos para integridade
UNIQUE_INDEXES = [
    IndexDefinition(
        name="uk_establ_cnpj_completo",
        table="estabelecimentos",
        columns=["cnpj_basico", "cnpj_ordem", "cnpj_dv"],
        unique=True
    ),
    IndexDefinition(
        name="uk_empresas_cnpj_basico",
        table="empresas",
        columns=["cnpj_basico"],
        unique=True
    ),
]

# Todos os índices (ordem de criação importante)
ALL_INDEXES = OPTIMIZATION_INDEXES + UNIQUE_INDEXES


def generate_sql_create_index(index_def: IndexDefinition) -> str:
    """Gera SQL CREATE INDEX para uma definição de índice."""
    if index_def.column_ops:
        columns_str = ", ".join(f"{col} {index_def.column_ops}" for col in index_def.columns)
    else:
        columns_str = ", ".join(index_def.columns)

    unique_clause = "UNIQUE " if index_def.unique else ""
    if_not_exists_clause = "IF NOT EXISTS " if index_def.if_not_exists else ""
    using_clause = f"USING {index_def.using} " if index_def.using else ""
    where_clause = f" WHERE {index_def.where}" if index_def.where else ""

    return (
        f"CREATE {unique_clause}INDEX {if_not_exists_clause}{index_def.name} "
        f"ON {index_def.table} {using_clause}({columns_str}){where_clause};"
    )


def generate_all_index_sql() -> List[str]:
    """Gera SQL para extensões + todos os índices definidos."""
    return list(REQUIRED_EXTENSIONS) + [generate_sql_create_index(idx) for idx in ALL_INDEXES]


def get_indexes_by_table(table_name: str) -> List[IndexDefinition]:
    """Retorna todos os índices para uma tabela específica."""
    return [idx for idx in ALL_INDEXES if idx.table == table_name]


def get_index_by_name(index_name: str) -> IndexDefinition:
    """Retorna uma definição de índice pelo nome."""
    for idx in ALL_INDEXES:
        if idx.name == index_name:
            return idx
    raise ValueError(f"Index '{index_name}' not found")
