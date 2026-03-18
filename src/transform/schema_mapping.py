"""
Definição dos Schemas para os dados da Receita Federal.
Corrigido para incluir a tabela SIMPLES (MEI) e Tabelas Auxiliares.
"""

# 1. EMPRESAS
EMPRESAS = {
    "columns": [
        "cnpj_basico", "razao_social", "natureza_juridica", "qualificacao_responsavel",
        "capital_social", "porte_empresa", "ente_federativo_responsavel"
    ],
    "types": {
        "cnpj_basico": "string",
        "razao_social": "string",
        "natureza_juridica": "string",
        "qualificacao_responsavel": "string",
        "capital_social": "float64",
        "porte_empresa": "string",
        "ente_federativo_responsavel": "string"
    }
}

# 2. ESTABELECIMENTOS
ESTABELECIMENTOS = {
    "columns": [
        "cnpj_basico", "cnpj_ordem", "cnpj_dv", "identificador_matriz_filial",
        "nome_fantasia", "situacao_cadastral", "data_situacao_cadastral",
        "motivo_situacao_cadastral", "nome_cidade_exterior", "pais",
        "data_inicio_atividade", "cnae_fiscal_principal", "cnae_fiscal_secundaria",
        "tipo_logradouro", "logradouro", "numero", "complemento", "bairro",
        "cep", "uf", "municipio", "ddd_1", "telefone_1", "ddd_2", "telefone_2",
        "ddd_fax", "fax", "correio_eletronico", "situacao_especial", "data_situacao_especial"
    ],
    "types": {
        "cnpj_basico": "string",
        "cnpj_ordem": "string",
        "cnpj_dv": "string",
        "situacao_cadastral": "string",
        "cep": "string",
        "uf": "string",
        "municipio": "string",
        "cnae_fiscal_principal": "string",
        "data_inicio_atividade": "string"
    }
}

# 3. SOCIOS
SOCIOS = {
    "columns": [
        "cnpj_basico", "identificador_socio", "nome_socio", "cnpj_cpf_socio",
        "qualificacao_socio", "data_entrada_sociedade", "pais",
        "representante_legal", "nome_representante", "qualificacao_representante", "faixa_etaria"
    ],
    "types": {
        "cnpj_basico": "string",
        "cnpj_cpf_socio": "string",
        "nome_socio": "string"
    }
}

# 4. SIMPLES (Crucial para identificar MEI)
SIMPLES = {
    "columns": [
        "cnpj_basico", "opcao_pelo_simples", "data_opcao_simples", "data_exclusao_simples",
        "opcao_pelo_mei", "data_opcao_mei", "data_exclusao_mei"
    ],
    "types": {
        "cnpj_basico": "string",
        "opcao_pelo_simples": "string",
        "opcao_pelo_mei": "string"
    }
}

# 5. TABELAS AUXILIARES
AUXILIARES = {
    "CNAES": ["codigo", "descricao"],
    "MUNICIPIOS": ["codigo", "descricao"],
    "NATUREZAS": ["codigo", "descricao"],
    "PAISES": ["codigo", "descricao"],
    "QUALIFICACOES": ["codigo", "descricao"],
    "MOTIVOS": ["codigo", "descricao"]
}


def get_columns_by_filename(filename: str):
    """
    Retorna a lista de colunas baseada no nome do arquivo.
    Funciona para .zip ou .parquet.
    """
    f = filename.upper()

    if "EMPRESAS" in f: return EMPRESAS["columns"]
    if "ESTABELE" in f: return ESTABELECIMENTOS["columns"]
    if "SOCIOS" in f: return SOCIOS["columns"]
    if "SIMPLES" in f: return SIMPLES["columns"]  # <--- Adicionado aqui

    # Busca exata ou parcial nas tabelas auxiliares
    for key, cols in AUXILIARES.items():
        if key in f:
            return cols

    return None