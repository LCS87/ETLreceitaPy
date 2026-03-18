"""
Definições centralizadas de índices do banco de dados.
Remove duplicação de código e facilita manutenção.
"""

from dataclasses import dataclass
from typing import List


@dataclass
class IndexDefinition:
    """Definição de um índice do banco de dados."""
    name: str
    table: str
    columns: List[str]
    unique: bool = False
    if_not_exists: bool = True


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
        columns=["codigo_municipio"]
    ),
    IndexDefinition(
        name="idx_establ_situacao",
        table="estabelecimentos",
        columns=["situacao_cadastral"]
    ),
    IndexDefinition(
        name="idx_establ_operadora",
        table="estabelecimentos",
        columns=["operadora_telefone"]
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
        columns=["operadora_telefone"]
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
    columns_str = ", ".join(index_def.columns)
    unique_clause = "UNIQUE " if index_def.unique else ""
    if_not_exists_clause = "IF NOT EXISTS " if index_def.if_not_exists else ""
    
    return (
        f"CREATE {unique_clause}INDEX {if_not_exists_clause}{index_def.name} "
        f"ON {index_def.table} ({columns_str});"
    )


def generate_all_index_sql() -> List[str]:
    """Gera SQL para todos os índices definidos."""
    return [generate_sql_create_index(idx) for idx in ALL_INDEXES]


def get_indexes_by_table(table_name: str) -> List[IndexDefinition]:
    """Retorna todos os índices para uma tabela específica."""
    return [idx for idx in ALL_INDEXES if idx.table == table_name]


def get_index_by_name(index_name: str) -> IndexDefinition:
    """Retorna uma definição de índice pelo nome."""
    for idx in ALL_INDEXES:
        if idx.name == index_name:
            return idx
    raise ValueError(f"Index '{index_name}' not found")
