"""
Factory para injeção de dependências do pipeline ELT.
Implementa Dependency Inversion Principle (DIP).
"""

from typing import Protocol
from pathlib import Path
from src.core.interfaces import DataExtractor, DataTransformer, DataLoader
from src.extract.async_download import AsyncDownloader
from src.transform.optimized_parquet_processor import OptimizedParquetProcessor
from src.load.postgres_adapter import PostgresLoader
from src.utils.env_loader import config


class ELTPipelineFactory:
    """Factory para criar instâncias do pipeline ELT com injeção de dependência."""
    
    @staticmethod
    def create_extractor() -> DataExtractor:
        """Cria instância de extrator de dados."""
        return AsyncDownloader(
            base_url=config.RECEITA_BASE_URL, 
            save_path=config.RAW_DIR
        )
    
    @staticmethod
    def create_transformer() -> DataTransformer:
        """Cria instância de transformador de dados com enriquecimento integrado."""
        return OptimizedParquetProcessor(
            raw_path=config.RAW_DIR, 
            silver_path=config.SILVER_DIR,
            chunk_size=config.CHUNK_SIZE
        )
    
    @staticmethod
    def create_loader() -> DataLoader:
        """Cria instância de carregador de dados."""
        return PostgresLoader(db_config=config.DATABASE_URL)
    
    @staticmethod
    def create_pipeline() -> 'ELTPipeline':
        """Cria pipeline completo com todas as dependências injetadas."""
        extractor = ELTPipelineFactory.create_extractor()
        transformer = ELTPipelineFactory.create_transformer()
        loader = ELTPipelineFactory.create_loader()
        
        return ELTPipeline(
            extractor=extractor,
            transformer=transformer,
            loader=loader
        )


class ELTPipeline:
    """Pipeline ELT com dependências injetadas."""
    
    def __init__(
        self,
        extractor: DataExtractor,
        transformer: DataTransformer,
        loader: DataLoader
    ) -> None:
        self.extractor = extractor
        self.transformer = transformer
        self.loader = loader
    
    async def run(self) -> None:
        """Executa o pipeline completo com tratamento de erros."""
        from src.core.interfaces import FatalError, RetryableError
        from src.monitoring.prometheus_stats import metrics
        from src.utils.log_handler import logger
        try:
            with metrics.track_duration(stage="pipeline_total"):
                logger.info("=== ETAPA 1: EXTRAÇÃO ===")
                files = await self.extractor.extract()
                if not files:
                    raise FatalError("Nenhum arquivo extraído — abortando pipeline")
                logger.info(f" {len(files)} arquivos extraídos")

                logger.info("=== ETAPA 2: TRANSFORMAÇÃO ===")
                self.transformer.transform(files)

                logger.info("=== ETAPA 3: CARGA ===")
                await self.loader.load()
            logger.info(" Pipeline concluído com sucesso")
            metrics.record_file(stage="pipeline", status="success")
        except FatalError as e:
            logger.error(f" Erro fatal no pipeline: {e}")
            metrics.record_file(stage="pipeline", status="fatal_error")
            raise
        except RetryableError as e:
            logger.warning(f" Erro retentável: {e}")
            metrics.record_file(stage="pipeline", status="retryable_error")
            raise
        except Exception as e:
            logger.error(f" Erro inesperado no pipeline: {e}", exc_info=True)
            metrics.record_file(stage="pipeline", status="error")
            raise
