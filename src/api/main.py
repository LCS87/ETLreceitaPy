"""
API REST para consulta aos dados processados do ETLreceitaPy.
Expõe endpoints para acesso seguro aos dados enriquecidos.
"""

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
import os
from datetime import datetime

# Models
from .models import Estabelecimento, Empresa, Socio
from .schemas import LeadDTO, LeadSearchRequest, PaginatedResponse

# Configuração da aplicação
app = FastAPI(
    title="ETLreceitaPy API",
    description="API REST para consulta de dados enriquecidos da Receita Federal",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, especificar origens permitidas
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuração do banco de dados
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost/receita")
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
async def root():
    """Health check endpoint."""
    return {
        "message": "ETLreceitaPy API",
        "version": "1.0.0",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/api/v1/leads", response_model=PaginatedResponse)
async def list_leads(
    uf: str = Query(..., min_length=2, max_length=2, example="SP"),
    operadora: Optional[str] = Query(None, example="VIVO"),
    categoria: Optional[str] = Query(None, example="ME"),
    situacao: Optional[str] = Query(None, example="02"),
    limit: int = Query(20, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db)
) -> PaginatedResponse:
    """
    Lista leads com filtros.
    
    Exemplo:
        GET /api/v1/leads?uf=SP&operadora=VIVO&limit=50
    """
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
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.get("/api/v1/leads/{cnpj_basico}", response_model=LeadDTO)
async def get_lead_by_cnpj(
    cnpj_basico: str = Field(..., min_length=8, max_length=8, description="CNPJ básico"),
    db: AsyncSession = Depends(get_db)
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
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.post("/api/v1/leads/buscar", response_model=PaginatedResponse)
async def search_leads(
    search_request: LeadSearchRequest,
    db: AsyncSession = Depends(get_db)
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
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.get("/api/v1/stats/ufs")
async def get_stats_by_uf(db: AsyncSession = Depends(get_db)):
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
                "percent_telefone": (com_telefone / total * 100) if total > 0 else 0,
                "percent_email": (com_email / total * 100) if total > 0 else 0
            })
        
        return {"data": stats, "total": len(stats)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


@app.get("/api/v1/stats/operadoras")
async def get_stats_by_operadora(db: AsyncSession = Depends(get_db)):
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
                "percent_total": (row.total_leads / total_geral * 100) if total_geral > 0 else 0
            })
        
        return {"data": stats, "total_leads": total_geral, "total_operadoras": len(stats)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
