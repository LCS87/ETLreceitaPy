"""
API REST para consulta aos dados processados do ETLreceitaPy.
Expõe endpoints para acesso seguro aos dados enriquecidos.
"""

import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Path, Depends, Security, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from starlette.middleware.base import BaseHTTPMiddleware

from src.utils.env_loader import config
from src.utils.log_handler import logger

# Rate limiting配置
RATE_LIMIT_REQUESTS = 100
RATE_LIMIT_WINDOW = 60  # seconds
_rate_limit_store: dict[str, list[float]] = defaultdict(list)

# Models
from .models import Estabelecimento, Empresa, Socio
from .schemas import LeadDTO, LeadSearchRequest, PaginatedResponse

# Configuração da aplicação
app = FastAPI(
    title="ETLreceitaPy API",
    description="""
    API REST para consulta de dados enriquecidos da Receita Federal.
    
    ## Funcionalidades
    - **Leads**: Consulta de leads segmentados por UF, operadora e categoria
    - **Estatísticas**: Métricas agregadas por UF e operadora
    - **Health**: Verificação de status e componentes
    
    ## Autenticação
    Utilize o header `X-API-Key` para autenticação (se configurado).
    
    ## Rate Limiting
    100 requests por minuto por IP.
    
    ## Contato
    Para dúvidas, contate a equipe de Data Engineering.
    """,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    contact={
        "name": "Data Engineering Team",
        "email": "data-engineering@empresa.com.br",
    },
    license_info={
        "name": "MIT License",
    },
)

# CORS middleware
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:5000,http://localhost:8001"
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)

# Adicionar middleware de rate limiting
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting: 100 requests por minuto por IP."""
    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        # Limpar registros antigos
        _rate_limit_store[client_ip] = [
            t for t in _rate_limit_store[client_ip] 
            if now - t < RATE_LIMIT_WINDOW
        ]
        
        if len(_rate_limit_store[client_ip]) >= RATE_LIMIT_REQUESTS:
            raise HTTPException(
                status_code=429, 
                detail=f"Rate limit excedido: {RATE_LIMIT_REQUESTS} requests por {RATE_LIMIT_WINDOW}s"
            )
        
        _rate_limit_store[client_ip].append(now)
        return await call_next(request)

app.add_middleware(RateLimitMiddleware)

# Autenticação: API Key (X-API-Key) ou JWT (Authorization: Bearer <token>)
from jose import JWTError, jwt
from src.api.auth import (
    ALGORITHM,
    SECRET_KEY,
    authenticate_user,
    create_token_for_user,
    get_current_user,
    optional_bearer,
)

API_KEY = os.getenv("API_KEY", "")
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=False)


async def verify_api_key(api_key: Optional[str] = Security(api_key_header)) -> None:
    """Verifica a API Key. Se API_KEY estiver vazia no .env, desabilita auth (modo dev)."""
    if not API_KEY:
        return
    if not api_key or api_key != API_KEY:
        raise HTTPException(status_code=403, detail="API Key inválida ou ausente")


async def verify_credentials(
    api_key: Optional[str] = Security(api_key_header),
    token: Optional[str] = Security(optional_bearer),
) -> Optional[Dict[str, Any]]:
    """Autenticação combinada: API Key OU JWT Bearer.

    Retorna o usuário do JWT (quando usado) ou None (API key / modo dev).
    """
    if not API_KEY:
        return None  # modo dev: auth desabilitada
    if api_key and api_key == API_KEY:
        return None
    if token:
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            raise HTTPException(
                status_code=401,
                detail="Token JWT inválido ou expirado",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if payload.get("sub"):
            return {"username": payload["sub"], "role": payload.get("role", "user")}
        raise HTTPException(
            status_code=401,
            detail="Token JWT sem subject",
            headers={"WWW-Authenticate": "Bearer"},
        )
    raise HTTPException(status_code=403, detail="API Key inválida ou ausente")


class LoginRequest(BaseModel):
    """Credenciais de login (usuário e senha em texto plano)."""
    username: str
    password: str


@app.post(
    "/api/v1/auth/login",
    tags=["Autenticação"],
    summary="Autenticar e obter token JWT",
    response_description="Token de acesso JWT",
    responses={
        401: {"description": "Usuário ou senha inválidos"},
        429: {"description": "Rate limit excedido"},
    },
)
async def login(credentials: LoginRequest) -> Dict[str, Any]:
    """Autentica usuário (arquivo de usuários + bcrypt) e emite token JWT."""
    user = authenticate_user(credentials.username, credentials.password)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Usuário ou senha inválidos",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token, expires_in = create_token_for_user(credentials.username, user)
    return {"access_token": token, "token_type": "bearer", "expires_in": expires_in}


@app.get(
    "/api/v1/auth/me",
    tags=["Autenticação"],
    summary="Identidade do token JWT atual",
    responses={401: {"description": "Token ausente, inválido ou expirado"}},
)
async def auth_me(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Retorna o usuário correspondente ao Bearer JWT enviado."""
    return current_user


# Configuração do banco de dados compartilhada com o restante do pipeline.
DATABASE_URL = config.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")
engine = create_async_engine(DATABASE_URL, echo=False)
async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    """Dependency para obter sessão do banco de dados."""
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


@app.get("/")
@app.get("/api/v1/health")
async def root() -> Dict[str, Any]:
    """Health check endpoint."""
    return {
        "message": "ETLreceitaPy API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@app.get("/api/v1/health/detailed")
async def detailed_health_check(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Health check detalhado com verificação de componentes.
    
    Verifica:
    - Conexão com banco de dados
    - Status do sistema
    - Versão da aplicação
    """
    health_status = {
        "status": "healthy",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "components": {}
    }
    
    # Verificar conexão com banco de dados
    try:
        await db.execute(text("SELECT 1"))
        health_status["components"]["database"] = {
            "status": "healthy",
            "response_time_ms": 0  # Poderia medir o tempo real
        }
    except Exception as e:
        health_status["status"] = "degraded"
        health_status["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e)
        }
    
    # Verificar espaço em disco
    try:
        import psutil
        disk = psutil.disk_usage('/')
        health_status["components"]["disk"] = {
            "status": "healthy" if disk.percent < 90 else "warning",
            "total_gb": round(disk.total / (1024**3), 2),
            "used_gb": round(disk.used / (1024**3), 2),
            "percent_used": disk.percent
        }
    except Exception as e:
        health_status["components"]["disk"] = {
            "status": "unknown",
            "error": str(e)
        }
    
    # Verificar memória
    try:
        import psutil
        memory = psutil.virtual_memory()
        health_status["components"]["memory"] = {
            "status": "healthy" if memory.percent < 90 else "warning",
            "total_gb": round(memory.total / (1024**3), 2),
            "used_gb": round(memory.used / (1024**3), 2),
            "percent_used": memory.percent
        }
    except Exception as e:
        health_status["components"]["memory"] = {
            "status": "unknown",
            "error": str(e)
        }
    
    return health_status


@app.get(
    "/api/v1/leads",
    response_model=PaginatedResponse,
    tags=["Leads"],
    summary="Listar leads com filtros",
    description="Lista leads segmentados por UF, operadora e categoria com paginação.",
    responses={
        200: {"description": "Leads encontrados", "model": PaginatedResponse},
        403: {"description": "API Key inválida"},
        404: {"description": "Nenhum lead encontrado para a UF informada"},
        429: {"description": "Rate limit excedido"},
    },
)
async def list_leads(
    uf: str = Query(..., min_length=2, max_length=2, examples=["SP"], description="UF (2 letras)"),
    operadora: Optional[str] = Query(None, examples=["VIVO"], description="Operadora de telefone"),
    categoria: Optional[str] = Query(None, examples=["ME"], description="Categoria da empresa"),
    situacao: Optional[str] = Query(None, examples=["02"], description="Situação cadastral"),
    limit: int = Query(20, ge=1, le=1000, description="Limite por página"),
    offset: int = Query(0, ge=0, description="Offset para paginação"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_credentials)
) -> PaginatedResponse:
    try:
        # Construir filtros
        conditions = [Estabelecimento.uf == uf.upper()]
        
        if operadora:
            conditions.append(Estabelecimento.operadora_telefone == operadora.upper())
        if categoria:
            conditions.append(Estabelecimento.categoria == categoria.upper())
        if situacao:
            conditions.append(Estabelecimento.situacao_cadastral == situacao)
        
        # Contar total
        count_stmt = select(func.count(Estabelecimento.cnpj_basico)).where(and_(*conditions))
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # Buscar dados
        query = select(Estabelecimento).where(and_(*conditions))
        query = query.offset(offset).limit(limit)
        
        result = await db.execute(query)
        leads = result.scalars().all()
        
        if not leads and offset == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Nenhum lead encontrado para UF={uf}"
            )
        
        return PaginatedResponse(
            data=[LeadDTO(**lead.to_dict()) for lead in leads],
            total=total,
            limit=limit,
            offset=offset,
            has_next=(offset + limit) < total,
            has_prev=offset > 0,
            page_count=(total + limit - 1) // limit if total > 0 else 0
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro em list_leads: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno do servidor. Consulte os logs.")


@app.get(
    "/api/v1/leads/{cnpj_basico}",
    response_model=LeadDTO,
    tags=["Leads"],
    summary="Buscar lead por CNPJ",
    description="Recupera um lead específico pelo CNPJ básico (8 dígitos).",
    responses={
        200: {"description": "Lead encontrado", "model": LeadDTO},
        404: {"description": "CNPJ não encontrado"},
    },
)
async def get_lead_by_cnpj(
    cnpj_basico: str = Path(..., min_length=8, max_length=8, description="CNPJ básico"),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_credentials)
) -> LeadDTO:
    """Recupera um lead específico pelo CNPJ básico."""
    try:
        query = select(Estabelecimento).where(Estabelecimento.cnpj_basico == cnpj_basico)
        
        result = await db.execute(query)
        lead = result.scalars().first()
        
        if not lead:
            raise HTTPException(
                status_code=404,
                detail=f"CNPJ {cnpj_basico} não encontrado"
            )
        
        return LeadDTO(**lead.to_dict())
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro em get_lead_by_cnpj: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno do servidor. Consulte os logs.")


@app.post(
    "/api/v1/leads/buscar",
    response_model=PaginatedResponse,
    tags=["Leads"],
    summary="Busca avançada de leads",
    description="Busca leads com múltiplos filtros: UFs, operadoras, categorias e situações.",
    responses={
        200: {"description": "Leads encontrados", "model": PaginatedResponse},
        403: {"description": "API Key inválida"},
    },
)
async def search_leads(
    search_request: LeadSearchRequest,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_credentials)
) -> PaginatedResponse:
    """Busca avançada com múltiplos filtros."""
    try:
        conditions = []
        
        if search_request.ufs:
            ufs_upper = [uf.upper() for uf in search_request.ufs]
            conditions.append(Estabelecimento.uf.in_(ufs_upper))
        
        if search_request.operadoras:
            ops_upper = [op.upper() for op in search_request.operadoras]
            conditions.append(Estabelecimento.operadora_telefone.in_(ops_upper))
        
        if search_request.categorias:
            cats_upper = [cat.upper() for cat in search_request.categorias]
            conditions.append(Estabelecimento.categoria.in_(cats_upper))
        
        if search_request.situacoes:
            conditions.append(Estabelecimento.situacao_cadastral.in_(search_request.situacoes))
        
        # Contar
        count_stmt = select(func.count(Estabelecimento.cnpj_basico))
        if conditions:
            count_stmt = count_stmt.where(and_(*conditions))
        
        total_result = await db.execute(count_stmt)
        total = total_result.scalar() or 0
        
        # Buscar
        query = select(Estabelecimento)
        if conditions:
            query = query.where(and_(*conditions))
        
        query = query.offset(search_request.offset).limit(search_request.limit)
        
        result = await db.execute(query)
        leads = result.scalars().all()
        
        return PaginatedResponse(
            data=[LeadDTO(**lead.to_dict()) for lead in leads],
            total=total,
            limit=search_request.limit,
            offset=search_request.offset,
            has_next=(search_request.offset + search_request.limit) < total,
            has_prev=search_request.offset > 0,
            page_count=(total + search_request.limit - 1) // search_request.limit if total > 0 else 0
        )
    
    except Exception as e:
        logger.error(f"Erro em search_leads: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno do servidor. Consulte os logs.")


@app.get(
    "/api/v1/stats/ufs",
    tags=["Estatísticas"],
    summary="Estatísticas por UF",
    description="Retorna métricas de leads agrupados por UF (total, com telefone, com email).",
    responses={
        200: {"description": "Estatísticas por UF"},
        403: {"description": "API Key inválida"},
    },
)
async def get_stats_by_uf(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_credentials)
) -> Dict[str, Any]:
    """Estatísticas de leads por UF."""
    try:
        query = select(
            Estabelecimento.uf,
            func.count(Estabelecimento.cnpj_basico).label("total_leads"),
            func.count(func.nullif(Estabelecimento.operadora_telefone, "")).label("com_telefone"),
            func.count(func.nullif(Estabelecimento.email, "")).label("com_email")
        ).group_by(Estabelecimento.uf).order_by(func.count(Estabelecimento.cnpj_basico).desc())
        
        result = await db.execute(query)
        rows = result.all()
        
        stats = []
        for row in rows:
            total = row.total_leads or 0
            com_telefone = row.com_telefone or 0
            com_email = row.com_email or 0
            
            stats.append({
                "uf": row.uf,
                "total_leads": total,
                "com_telefone": com_telefone,
                "com_email": com_email,
                "percent_telefone": round((com_telefone / total * 100), 2) if total > 0 else 0.0,
                "percent_email": round((com_email / total * 100), 2) if total > 0 else 0.0
            })
        
        return {"data": stats, "total": len(stats)}
        
    except Exception as e:
        logger.error(f"Erro em get_stats_by_uf: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno do servidor. Consulte os logs.")


@app.get(
    "/api/v1/stats/operadoras",
    tags=["Estatísticas"],
    summary="Estatísticas por operadora",
    description="Retorna métricas de leads agrupados por operadora de telefone.",
    responses={
        200: {"description": "Estatísticas por operadora"},
        403: {"description": "API Key inválida"},
    },
)
async def get_stats_by_operadora(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(verify_credentials)
) -> Dict[str, Any]:
    """Estatísticas de leads por operadora de telefone."""
    try:
        query = select(
            Estabelecimento.operadora_telefone,
            func.count(Estabelecimento.cnpj_basico).label("total_leads")
        ).where(
            func.nullif(Estabelecimento.operadora_telefone, "").isnot(None)
        ).group_by(Estabelecimento.operadora_telefone).order_by(
            func.count(Estabelecimento.cnpj_basico).desc()
        )
        
        result = await db.execute(query)
        rows = result.all()
        
        total_geral = sum(row.total_leads for row in rows)
        
        stats = []
        for row in rows:
            stats.append({
                "operadora": row.operadora_telefone or "SEM_OPERADORA",
                "total_leads": row.total_leads,
                "percent_total": round((row.total_leads / total_geral * 100), 2) if total_geral > 0 else 0.0
            })
        
        return {"data": stats, "total_leads": total_geral, "total_operadoras": len(stats)}
        
    except Exception as e:
        logger.error(f"Erro em get_stats_by_operadora: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Erro interno do servidor. Consulte os logs.")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)

