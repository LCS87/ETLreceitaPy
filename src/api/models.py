"""
Models SQLAlchemy para a API REST do ETLreceitaPy.
Define as tabelas do banco de dados para ORM.
"""

from sqlalchemy import Column, String, Integer, Numeric, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    """Base declarativa para models SQLAlchemy."""
    pass


class Estabelecimento(Base):
    """Model para tabela de estabelecimentos."""
    __tablename__ = "estabelecimentos"
    
    cnpj_basico = Column(String(8), primary_key=True)
    cnpj_ordem = Column(String(4), primary_key=True)
    cnpj_dv = Column(String(2), primary_key=True)
    
    # Identificação
    nome_fantasia = Column(String(200))
    situacao_cadastral = Column(String(2))
    data_situacao_cadastral = Column(String(8))
    motivo_situacao_cadastral = Column(String(2))
    
    # Endereço
    tipo_logradouro = Column(String(100))
    logradouro = Column(String(500))
    numero = Column(String(20))
    complemento = Column(String(200))
    bairro = Column(String(200))
    cep = Column(String(8))
    uf = Column(String(2))
    codigo_municipio = Column(String(7))
    nome_cidade_exterior = Column(String(100))
    codigo_pais = Column(String(3))
    
    # Contato
    ddd_1 = Column(String(2))
    telefone_1 = Column(String(9))
    ddd_2 = Column(String(2))
    telefone_2 = Column(String(9))
    ddd_fax = Column(String(2))
    telefone_fax = Column(String(9))
    email = Column(String(200))
    
    # Negócio
    data_inicio_atividade = Column(String(8))
    cnae_fiscal_principal = Column(String(7))
    cnae_fiscal_secundaria = Column(Text)
    
    # Situação especial
    situacao_especial = Column(String(2))
    data_situacao_especial = Column(String(8))
    
    # Campos enriquecidos
    operadora_telefone = Column(String(50))
    categoria = Column(String(20))
    
    def to_dict(self):
        """Converte para dicionário."""
        return {
            'cnpj_basico': self.cnpj_basico,
            'cnpj_ordem': self.cnpj_ordem,
            'cnpj_dv': self.cnpj_dv,
            'nome_fantasia': self.nome_fantasia,
            'situacao_cadastral': self.situacao_cadastral,
            'uf': self.uf,
            'codigo_municipio': self.codigo_municipio,
            'ddd_1': self.ddd_1,
            'telefone_1': self.telefone_1,
            'ddd_2': self.ddd_2,
            'telefone_2': self.telefone_2,
            'email': self.email,
            'data_inicio_atividade': self.data_inicio_atividade,
            'cnae_fiscal_principal': self.cnae_fiscal_principal,
            'operadora_telefone': self.operadora_telefone,
            'categoria': self.categoria
        }


class Empresa(Base):
    """Model para tabela de empresas."""
    __tablename__ = "empresas"
    
    cnpj_basico = Column(String(8), primary_key=True)
    razao_social = Column(String(500))
    natureza_juridica = Column(String(4))
    qualificacao_responsavel = Column(String(2))
    capital_social = Column(Numeric(14, 2))
    porte_empresa = Column(String(2))
    ente_federativo_responsavel = Column(String(20))
    
    def to_dict(self):
        """Converte para dicionário."""
        return {
            'cnpj_basico': self.cnpj_basico,
            'razao_social': self.razao_social,
            'natureza_juridica': self.natureza_juridica,
            'qualificacao_responsavel': self.qualificacao_responsavel,
            'capital_social': float(self.capital_social) if self.capital_social else 0,
            'porte_empresa': self.porte_empresa,
            'ente_federativo_responsavel': self.ente_federativo_responsavel
        }


class Socio(Base):
    """Model para tabela de sócios."""
    __tablename__ = "socios"
    
    cnpj_basico = Column(String(8), primary_key=True)
    identificador_socio = Column(Integer, primary_key=True)
    nome_socio = Column(String(500))
    cnpj_cpf_socio = Column(String(14))
    qualificacao_socio = Column(String(2))
    data_entrada_sociedade = Column(String(8))
    pais = Column(String(3))
    representante_legal = Column(String(14))
    nome_representante = Column(String(500))
    qualificacao_representante = Column(String(2))
    faixa_etaria = Column(String(2))
    
    def to_dict(self):
        """Converte para dicionário."""
        return {
            'cnpj_basico': self.cnpj_basico,
            'identificador_socio': self.identificador_socio,
            'nome_socio': self.nome_socio,
            'cnpj_cpf_socio': self.cnpj_cpf_socio,
            'qualificacao_socio': self.qualificacao_socio,
            'data_entrada_sociedade': self.data_entrada_sociedade,
            'pais': self.pais,
            'representante_legal': self.representante_legal,
            'nome_representante': self.nome_representante,
            'qualificacao_representante': self.qualificacao_representante,
            'faixa_etaria': self.faixa_etaria
        }
