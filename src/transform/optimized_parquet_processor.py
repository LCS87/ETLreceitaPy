"""
Processador Parquet otimizado com enriquecimento integrado e processamento paralelo.
"""
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
import zipfile
from typing import List, Optional
from concurrent.futures import ProcessPoolExecutor, as_completed

from src.transform.schema_mapping import get_columns_by_filename
from src.core.interfaces import SkippableError
from src.utils.phone_processor_vectorized import PhoneProcessorVectorized
from src.services.business_rules import filtrar_emails_contabilidade
from src.utils.log_handler import logger
from src.utils.env_loader import config


def _process_file_worker(zip_path_str: str, output_path_str: str, columns: list, chunk_size: int) -> None:
    """Função top-level para execução em processo separado (ProcessPoolExecutor)"""
    processor = OptimizedParquetProcessor(
        raw_path=Path(zip_path_str).parent,
        silver_path=Path(output_path_str).parent,
        chunk_size=chunk_size
    )
    processor._process_zip_with_enrichment(Path(zip_path_str), Path(output_path_str), columns)


class OptimizedParquetProcessor:
    """
    Processador Parquet com enriquecimento integrado.
    
    Otimizações:
    1. Enriquecimento durante conversão (não depois)
    2. Processamento em chunks configuráveis
    3. Compressão snappy
    4. Vetorização de telefonia
    """
    
    def __init__(self, 
                 raw_path: Path, 
                 silver_path: Path,
                 chunk_size: int = 500000,
                 phone_processor: Optional[PhoneProcessorVectorized] = None):
        self.raw_path = Path(raw_path)
        self.silver_path = Path(silver_path)
        self.chunk_size = chunk_size
        self.phone_processor = phone_processor or PhoneProcessorVectorized()
        self.silver_path.mkdir(parents=True, exist_ok=True)
        # Usa MAX_WORKERS do config, mas limita a 6 para não saturar I/O do NVMe
        self.max_workers = min(config.MAX_WORKERS, 6)

    def transform(self, files: List[Path]) -> None:
        """Transforma ZIPs em Parquet enriquecido — arquivos diferentes em paralelo"""
        pending = []
        for file_path in files:
            output_path = self.silver_path / file_path.name.replace('.zip', '.parquet')
            if output_path.exists() and output_path.stat().st_size > 1024:
                logger.info(f"Pulando {file_path.name} (Parquet ja existe)")
                continue
            columns = get_columns_by_filename(file_path.name)
            if not columns:
                logger.warning(f"Schema nao encontrado para {file_path.name}. Pulando...")
                continue
            pending.append((file_path, output_path, columns))

        if not pending:
            return

        logger.info(f"Transformando {len(pending)} arquivos com {self.max_workers} workers paralelos...")

        # Arquivos grandes (>500MB) processados separadamente para não competir por RAM
        large = [(f, o, c) for f, o, c in pending if f.stat().st_size > 500 * 1024 * 1024]
        small = [(f, o, c) for f, o, c in pending if f.stat().st_size <= 500 * 1024 * 1024]

        # Processa arquivos pequenos em paralelo
        if small:
            with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(_process_file_worker, str(f), str(o), c, self.chunk_size): f.name
                    for f, o, c in small
                }
                for future in as_completed(futures):
                    name = futures[future]
                    try:
                        future.result()
                        logger.info(f"Concluido: {name}")
                    except Exception as e:
                        logger.error(f"Erro em {name}: {e}")

        # Processa arquivos grandes sequencialmente (evita OOM)
        for file_path, output_path, columns in large:
            logger.info(f"Transformando (grande) {file_path.name}...")
            try:
                self._process_zip_with_enrichment(file_path, output_path, columns)
                logger.info(f"Concluido: {file_path.name}")
            except Exception as e:
                logger.error(f"Erro em {file_path.name}: {e}")
                if output_path.exists():
                    output_path.unlink()

    def _process_zip_with_enrichment(self, zip_path: Path, output_path: Path, columns: List[str]) -> None:
        """Processa ZIP aplicando enriquecimento em cada chunk"""
        if not zip_path.exists():
            raise FileNotFoundError(f"ZIP não encontrado: {zip_path}")
        
        try:
            z = zipfile.ZipFile(zip_path, 'r')
            csv_files = [f for f in z.namelist() if f.endswith('.csv') or '.csv' in f]
            internal_file = csv_files[0] if csv_files else z.namelist()[0]
            
            # Lê CSV em chunks
            reader = pd.read_csv(
                z.open(internal_file),
                sep=';',
                header=None,
                names=columns,
                encoding='latin-1',
                chunksize=self.chunk_size,
                dtype=str,
                low_memory=False,
                on_bad_lines='skip'
            )
            
            # Cria schema Arrow
            arrow_schema = pa.schema([pa.field(col, pa.string()) for col in columns])
            writer = None
            
            try:
                for chunk in reader:
                    # Aplica enriquecimento
                    enriched_chunk = self._enrich_chunk(chunk, columns)
                    
                    # Atualiza schema se necessário (novas colunas)
                    if writer is None:
                        arrow_schema = pa.Schema.from_pandas(enriched_chunk, preserve_index=False)
                        writer = pq.ParquetWriter(output_path, arrow_schema, compression='snappy')
                    
                    # Escreve chunk enriquecido
                    table = pa.Table.from_pandas(enriched_chunk, schema=arrow_schema, preserve_index=False)
                    writer.write_table(table)
                
                if writer:
                    writer.close()
                    
            except Exception as e:
                if writer:
                    writer.close()
                raise e
                
        except zipfile.BadZipFile as e:
            raise SkippableError(f"ZIP corrompido: {zip_path}") from e

    def _enrich_chunk(self, df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
        """
        Aplica todas as transformações de enriquecimento.
        
        Transformações:
        1. Telefonia (vetorizada)
        2. Limpeza de emails
        3. Categorização de negócio
        """
        import time
        from src.monitoring.prometheus_stats import metrics
        
        start_time = time.time()
        rows_count = len(df)
        
        # Normaliza dados (strings vazias)
        for col in columns:
            if col in df.columns:
                df[col] = df[col].astype(str).replace(['nan', 'None', 'NaN', 'nan'], '')
        
        # 1. Processamento de Telefonia (vetorizado)
        if 'ddd_1' in df.columns and 'telefone_1' in df.columns:
            try:
                df = self.phone_processor.process_batch(df)
                logger.debug(f"Telefonia processada: {len(df)} registros")
            except Exception as e:
                logger.warning(f"Erro no processamento de telefonia: {e}")
                # Fallback: cria colunas vazias
                df['telefone'] = ''
                df['operadora'] = 'ERRO_PROCESSING'
        
        # 2. Limpeza de Emails
        if 'correio_eletronico' in df.columns:
            try:
                df['correio_eletronico'] = df['correio_eletronico'].apply(
                    lambda x: filtrar_emails_contabilidade(x) if x and x != '' else ''
                )
                logger.debug(f"Emails limpos: {len(df)} registros")
            except Exception as e:
                logger.warning(f"Erro na limpeza de emails: {e}")
        
        # 3. Categorização de Negócio (tipo de empresa)
        if 'razao_social' in df.columns:
            try:
                df['categoria'] = df['razao_social'].apply(self._classificar_tipo_empresa)
                logger.debug(f"Empresas categorizadas: {len(df)} registros")
            except Exception as e:
                logger.warning(f"Erro na categorização: {e}")
                df['categoria'] = 'DESCONHECIDO'
        
        # Registra métricas (Task 9.2)
        duration = time.time() - start_time
        if duration > 0:
            throughput = rows_count / duration
            metrics.record_enrichment_throughput(throughput)
        
        return df
    
    def _classificar_tipo_empresa(self, razao_social: str) -> str:
        """
        Classifica tipo de empresa baseado na razão social.
        Simplificado para performance.
        """
        if not razao_social or razao_social == '':
            return 'DESCONHECIDO'
        
        razao = str(razao_social).upper()
        
        # LTDA / S.A.
        if any(x in razao for x in [' LTDA', ' S/A', ' SOCIEDADE', ' S.A.', 'LIMITADA']):
            return 'LTDA'
        
        # ME / EPP
        if any(x in razao for x in [' ME', ' EPP', 'MICROEMPRESA', 'PEQUENO PORTE']):
            return 'ME'
        
        # MEI (geralmente não tem sufixo)
        return 'MEI'
