"""
Schemas Pydantic para a API REST.
Define contratos de dados para serialização/deserialização.
"""

from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime
import re


class BaseDTO(BaseModel):
    """Base DTO com configurações comuns."""
    
    class Config:
        from_attributes = True
        str_strip_whitespace = True
        validate_assignment = True


class CNPJMixin(BaseModel):
    """Mixin para validação de CNPJ."""
    
    cnpj_basico: str = Field(..., min_length=8, max_length=8, description="CNPJ básico (8 dígitos)")
    cnpj_ordem: str = Field(..., min_length=4, max_length=4, description="CNPJ ordem (4 dígitos)")
    cnpj_dv: str = Field(..., min_length=2, max_length=2, description="Dígito verificador (2 dígitos)")
    
    @validator('cnpj_basico', 'cnpj_ordem', 'cnpj_dv')
    def validate_digits(cls, v):
        """Valida que contém apenas dígitos."""
        if not v.isdigit():
            raise ValueError('Deve conter apenas dígitos')
        return v
    
    @property
    def cnpj_completo(self) -> str:
        """Retorna CNPJ completo formatado."""
        return f"{self.cnpj_basico}{self.cnpj_ordem}{self.cnpj_dv}"
    
    @property
    def cnpj_formatado(self) -> str:
        """Retorna CNPJ formatado com pontuação."""
        cnpj = self.cnpj_completo
        return f"{cnpj[:2]}.{cnpj[2:5]}.{cnpj[5:8]}/{cnpj[8:12]}-{cnpj[12:]}"


class EnderecoDTO(BaseModel):
    """DTO para informações de endereço."""
    
    logradouro: Optional[str] = Field(None, description="Logradouro")
    numero: Optional[str] = Field(None, description="Número")
    complemento: Optional[str] = Field(None, description="Complemento")
    bairro: Optional[str] = Field(None, description="Bairro")
    cep: Optional[str] = Field(None, description="CEP")
    uf: str = Field(..., min_length=2, max_length=2, description="UF")
    codigo_municipio: Optional[str] = Field(None, description="Código do município")
    municipio: Optional[str] = Field(None, description="Nome do município")
    
    @validator('uf')
    def validate_uf(cls, v):
        """Valida formato da UF."""
        if not v.isalpha() or len(v) != 2:
            raise ValueError('UF deve ter 2 letras')
        return v.upper()
    
    @validator('cep')
    def validate_cep(cls, v):
        """Valida formato do CEP."""
        if v and not re.match(r'^\d{5}-?\d{3}$', v):
            raise ValueError('CEP deve estar no formato 00000-000')
        return v


class TelefoneDTO(BaseModel):
    """DTO para informações de telefone."""
    
    ddd_1: Optional[str] = Field(None, description="DDD do telefone 1")
    telefone_1: Optional[str] = Field(None, description="Telefone 1")
    ddd_2: Optional[str] = Field(None, description="DDD do telefone 2")
    telefone_2: Optional[str] = Field(None, description="Telefone 2")
    operadora_telefone: Optional[str] = Field(None, description="Operadora detectada")
    
    @validator('ddd_1', 'ddd_2')
    def validate_ddd(cls, v):
        """Valida formato do DDD."""
        if v and not re.match(r'^\d{2}$', v):
            raise ValueError('DDD deve ter 2 dígitos')
        return v
    
    @validator('telefone_1', 'telefone_2')
    def validate_telefone(cls, v):
        """Valida formato do telefone."""
        if v and not re.match(r'^\d{8,9}$', v):
            raise ValueError('Telefone deve ter 8 ou 9 dígitos')
        return v


class EmpresaDTO(BaseDTO, CNPJMixin):
    """DTO para dados da empresa."""
    
    razao_social: Optional[str] = Field(None, description="Razão social")
    nome_fantasia: Optional[str] = Field(None, description="Nome fantasia")
    natureza_juridica: Optional[str] = Field(None, description="Código da natureza jurídica")
    qualificacao_responsavel: Optional[str] = Field(None, description="Qualificação do responsável")
    capital_social: Optional[str] = Field(None, description="Capital social")
    porte_empresa: Optional[str] = Field(None, description="Porte da empresa")
    ente_federativo_responsavel: Optional[str] = Field(None, description="Ente federativo responsável")


class EstabelecimentoDTO(BaseDTO, CNPJMixin):
    """DTO para dados do estabelecimento."""
    
    nome_fantasia: Optional[str] = Field(None, description="Nome fantasia")
    situacao_cadastral: str = Field(..., description="Situação cadastral")
    data_situacao_cadastral: Optional[str] = Field(None, description="Data da situação cadastral")
    motivo_situacao_cadastral: Optional[str] = Field(None, description="Motivo da situação cadastral")
    nome_cidade_exterior: Optional[str] = Field(None, description="Nome da cidade no exterior")
    codigo_pais: Optional[str] = Field(None, description="Código do país")
    data_inicio_atividade: Optional[str] = Field(None, description="Data de início de atividade")
    cnae_fiscal_principal: Optional[str] = Field(None, description="CNAE fiscal principal")
    cnae_fiscal_secundaria: Optional[str] = Field(None, description="CNAE fiscal secundária")
    tipo_logradouro: Optional[str] = Field(None, description="Tipo de logradouro")
    logradouro: Optional[str] = Field(None, description="Logradouro")
    numero: Optional[str] = Field(None, description="Número")
    complemento: Optional[str] = Field(None, description="Complemento")
    bairro: Optional[str] = Field(None, description="Bairro")
    cep: Optional[str] = Field(None, description="CEP")
    uf: str = Field(..., min_length=2, max_length=2, description="UF")
    codigo_municipio: Optional[str] = Field(None, description="Código do município")
    municipio: Optional[str] = Field(None, description="Nome do município")
    ddd_1: Optional[str] = Field(None, description="DDD do telefone 1")
    telefone_1: Optional[str] = Field(None, description="Telefone 1")
    ddd_2: Optional[str] = Field(None, description="DDD do telefone 2")
    telefone_2: Optional[str] = Field(None, description="Telefone 2")
    ddd_fax: Optional[str] = Field(None, description="DDD do fax")
    telefone_fax: Optional[str] = Field(None, description="Telefone do fax")
    email: Optional[str] = Field(None, description="Email")
    situacao_especial: Optional[str] = Field(None, description="Situação especial")
    data_situacao_especial: Optional[str] = Field(None, description="Data da situação especial")
    
    # Campos enriquecidos
    operadora_telefone: Optional[str] = Field(None, description="Operadora detectada")
    categoria: Optional[str] = Field(None, description="Categoria do negócio")
    
    @validator('email')
    def validate_email(cls, v):
        """Valida formato do email."""
        if v and v.strip():
            email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
            if not re.match(email_pattern, v):
                raise ValueError('Email inválido')
        return v.strip() if v else None


class LeadDTO(BaseDTO, CNPJMixin):
    """DTO simplificado para leads (visão de negócio)."""
    
    nome_fantasia: Optional[str] = Field(None, description="Nome fantasia")
    razao_social: Optional[str] = Field(None, description="Razão social")
    situacao_cadastral: str = Field(..., description="Situação cadastral")
    uf: str = Field(..., min_length=2, max_length=2, description="UF")
    codigo_municipio: Optional[str] = Field(None, description="Código do município")
    municipio: Optional[str] = Field(None, description="Nome do município")
    ddd_1: Optional[str] = Field(None, description="DDD do telefone 1")
    telefone_1: Optional[str] = Field(None, description="Telefone 1")
    operadora_telefone: Optional[str] = Field(None, description="Operadora detectada")
    email: Optional[str] = Field(None, description="Email")
    cnae_fiscal_principal: Optional[str] = Field(None, description="CNAE fiscal principal")
    categoria: Optional[str] = Field(None, description="Categoria do negócio")
    capital_social: Optional[str] = Field(None, description="Capital social")
    porte_empresa: Optional[str] = Field(None, description="Porte da empresa")
    data_inicio_atividade: Optional[str] = Field(None, description="Data de início de atividade")


class LeadSearchRequest(BaseModel):
    """Request para busca avançada de leads."""
    
    ufs: List[str] = Field(default=[], description="Lista de UFs para filtrar")
    operadoras: List[str] = Field(default=[], description="Lista de operadoras")
    categorias: List[str] = Field(default=[], description="Lista de categorias")
    situacoes: List[str] = Field(default=[], description="Lista de situações cadastrais")
    cnaes: List[str] = Field(default=[], description="Lista de CNAEs")
    portes: List[str] = Field(default=[], description="Lista de portes de empresa")
    data_abertura_min: Optional[str] = Field(None, description="Data de abertura mínima (YYYY-MM-DD)")
    data_abertura_max: Optional[str] = Field(None, description="Data de abertura máxima (YYYY-MM-DD)")
    capital_min: Optional[float] = Field(None, ge=0, description="Capital social mínimo")
    capital_max: Optional[float] = Field(None, ge=0, description="Capital social máximo")
    tem_telefone: Optional[bool] = Field(None, description="Filtrar por tem telefone")
    tem_email: Optional[bool] = Field(None, description="Filtrar por tem email")
    limit: int = Field(default=100, ge=1, le=1000, description="Limite de resultados")
    offset: int = Field(default=0, ge=0, description="Offset para paginação")
    sort_by: Optional[str] = Field(default="nome_fantasia", description="Campo de ordenação")
    sort_order: Optional[str] = Field(default="asc", regex="^(asc|desc)$", description="Ordem de ordenação")
    
    @validator('ufs', 'operadoras', 'categorias', 'situacoes', 'cnaes', 'portes')
    def validate_lists(cls, v):
        """Valida que listas não contenham elementos vazios."""
        return [item.strip().upper() for item in v if item.strip()]
    
    @validator('data_abertura_min', 'data_abertura_max')
    def validate_dates(cls, v):
        """Valida formato das datas."""
        if v:
            try:
                datetime.strptime(v, '%Y-%m-%d')
            except ValueError:
                raise ValueError('Data deve estar no formato YYYY-MM-DD')
        return v


class PaginatedResponse(BaseModel):
    """Response paginado genérico."""
    
    data: List[LeadDTO]
    total: int = Field(..., ge=0, description="Total de registros")
    limit: int = Field(..., ge=1, le=1000, description="Limite por página")
    offset: int = Field(..., ge=0, description="Offset atual")
    has_next: bool = Field(..., description="Tem próxima página?")
    has_prev: bool = Field(..., description="Tem página anterior?")
    page_count: int = Field(..., ge=0, description="Total de páginas")
    
    @validator('page_count')
    def calculate_page_count(cls, v, values):
        """Calcula número total de páginas."""
        total = values.get('total', 0)
        limit = values.get('limit', 1)
        return (total + limit - 1) // limit if total > 0 else 0
    
    @validator('has_next')
    def calculate_has_next(cls, v, values):
        """Calcula se tem próxima página."""
        offset = values.get('offset', 0)
        limit = values.get('limit', 1)
        total = values.get('total', 0)
        return offset + limit < total
    
    @validator('has_prev')
    def calculate_has_prev(cls, v, values):
        """Calcula se tem página anterior."""
        offset = values.get('offset', 0)
        return offset > 0


class StatsUFDTO(BaseModel):
    """DTO para estatísticas por UF."""
    
    uf: str = Field(..., description="UF")
    total_leads: int = Field(..., ge=0, description="Total de leads")
    com_telefone: int = Field(..., ge=0, description="Leads com telefone")
    com_email: int = Field(..., ge=0, description="Leads com email")
    percent_telefone: float = Field(..., ge=0, le=100, description="% com telefone")
    percent_email: float = Field(..., ge=0, le=100, description="% com email")
    
    @validator('percent_telefone', 'percent_email')
    def calculate_percentages(cls, v, values):
        """Calcula percentuais."""
        total = values.get('total_leads', 1)
        return (v / total * 100) if total > 0 else 0


class StatsOperadoraDTO(BaseModel):
    """DTO para estatísticas por operadora."""
    
    operadora: str = Field(..., description="Operadora")
    total_leads: int = Field(..., ge=0, description="Total de leads")
    percent_total: float = Field(..., ge=0, le=100, description="% do total")
    
    @validator('percent_total')
    def calculate_percent_total(cls, v, values):
        """Calcula percentual do total (precisa do total geral)."""
        # Este campo será calculado no endpoint
        return v


class APIResponse(BaseModel):
    """Response genérico da API."""
    
    success: bool = Field(..., description="Sucesso da operação")
    message: str = Field(..., description="Mensagem de status")
    data: Optional[dict] = Field(None, description="Dados retornados")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp da resposta")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ErrorResponse(BaseModel):
    """DTO para respostas de erro."""
    
    success: bool = Field(default=False, description="Sempre False para erros")
    error_code: str = Field(..., description="Código do erro")
    message: str = Field(..., description="Mensagem de erro")
    details: Optional[dict] = Field(None, description="Detalhes adicionais")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="Timestamp do erro")
    
    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
