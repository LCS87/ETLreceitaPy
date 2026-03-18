"""
Interfaces e Protocolos para o pipeline ELT.
Implementa Dependency Inversion Principle (DIP) para desacoplar componentes.
"""

from typing import Protocol, List, Any
from pathlib import Path  # <--- O Path vem daqui!


class DataExtractor(Protocol):
    """Interface para extratores de dados."""
    
    async def extract(self) -> List[Path]:
        """Extrai dados e retorna lista de arquivos processados."""
        ...


class DataTransformer(Protocol):
    """Interface para transformadores de dados."""
    
    def transform(self, files: List[Path]) -> None:
        """Transforma os arquivos de entrada."""
        ...


class DataLoader(Protocol):
    """Interface para carregadores de dados."""
    
    async def load(self) -> None:
        """Carrega dados transformados no destino final."""
        ...


class ChunkNormalizer(Protocol):
    """Interface para normalização de chunks."""
    
    def normalize(self, df: Any, columns: List[str]) -> Any:
        """Normaliza um chunk de dados."""
        ...


class MetricsCollector(Protocol):
    """Interface para coleta de métricas."""
    
    def track_duration(self, stage: str):
        """Context manager para tracking de duração."""
        ...

    def record_file(self, stage: str, status: str) -> None:
        """Registra status de processamento de arquivo."""
        ...

    def record_rows(self, table_name: str, count: int) -> None:
        """Registra contagem de linhas processadas."""
        ...


class ELTError(Exception):
    """Base exception para erros do pipeline ELT."""
    pass


class RetryableError(ELTError):
    """Erro que pode ser retentado."""
    pass


class SkippableError(ELTError):
    """Erro que pode ser ignorado (skip)."""
    pass


class FatalError(ELTError):
    """Erro fatal que para o pipeline."""
    pass


class ValidationError(ELTError):
    """Erro de validação de dados."""
    pass


class ConfigurationError(ELTError):
    """Erro de configuração."""
    pass
