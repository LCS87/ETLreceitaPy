import asyncio
import sys
from pathlib import Path

# Configurações e Logs
from src.utils.env_loader import config
from src.utils.log_handler import logger
from src.config.pipeline_factory import ELTPipelineFactory
from src.monitoring.prometheus_stats import metrics
from src.core.interfaces import SkippableError, FatalError

# Adaptadores e Exportadores
from src.load.postgres_adapter import PostgresLoader
from src.exports.nordeste_exporter_optimized import exporter_optimized as exporter


async def wait_for_db():
    """Aguarda o PostgreSQL estar pronto para aceitar conexões (importante para Big Data)."""
    max_retries = 15
    for i in range(max_retries):
        try:
            loader = PostgresLoader(db_config=config.DATABASE_URL)
            # Tenta uma conexão simples
            with loader.engine.connect() as conn:
                logger.info("PostgreSQL esta pronto e aceitando conexoes!")
                return True
        except Exception:
            logger.warning(f"Banco de dados em recuperação ou iniciando... Tentativa {i+1}/{max_retries}")
            await asyncio.sleep(10) # Aguarda 10 segundos antes de tentar de novo
    return False

async def run_pipeline():
    logger.info(f"--- Iniciando Pipeline ELT - Host: {config.HOSTNAME} | Perfil: {config.PROFILE} ---")
    config.validate()

    # BLOCO CRÍTICO: Aguardar o Banco de Dados
    if not await wait_for_db():
        raise FatalError("O PostgreSQL não ficou pronto a tempo. Abortando pipeline.")

    try:
        # 1. ETAPA: DOWNLOAD E CONVERSÃO COM ENRIQUECIMENTO INTEGRADO
        # Nota: O enriquecimento agora acontece DURANTE a conversão CSV→Parquet
        # usando OptimizedParquetProcessor, eliminando a etapa separada anterior
        pipeline = ELTPipelineFactory.create_pipeline()
        
        with metrics.track_duration(stage="pipeline_run"):
            await pipeline.run()

            if not list(config.RAW_DIR.glob("*.zip")):
                raise FatalError("Nenhum arquivo encontrado para processar.")
            
            logger.info("Conversão e enriquecimento integrado concluídos")
            metrics.record_file(stage="transform", status="success")

        # A carga e a criação dos índices já são executadas por pipeline.run()
        # através do DataLoader injetado pela ELTPipelineFactory.
        logger.info("Carga e índices concluídos pelo pipeline principal")

        # 5. ETAPA: EXPORTAÇÃO DE LEADS (JOIN FINAL)
        with metrics.track_duration(stage="export_csv"):
            logger.info("--- Passo 5: Exportação de Leads Nordeste direto do Banco ---")
            # Este método export_from_db deve estar no seu nordeste_leads.py
            exporter.export_from_db() 
            logger.info("Exportação de arquivos CSV concluída!")

        logger.info("--- Pipeline finalizado com sucesso! ---")
        metrics.record_file(stage="pipeline", status="success")

    except FatalError as e:
        logger.error(f"--- Falha crítica: {e} ---")
        metrics.record_file(stage="pipeline", status="failed")
        raise
    
    except Exception as e:
        logger.error(f"--- Erro inesperado: {e} ---", exc_info=True)
        metrics.record_file(stage="pipeline", status="failed")
        raise

if __name__ == "__main__":
    if sys.platform == 'win32':
        import subprocess
        subprocess.run(['chcp', '65001'], shell=True, capture_output=True)
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    print("--- Servidor de métricas rodando na porta 8000 ---")

    try:
        asyncio.run(run_pipeline())
    except KeyboardInterrupt:
        logger.info("--- Pipeline interrompido pelo usuário. ---")
    finally:
        logger.info("--- Encerrando aplicação. ---")