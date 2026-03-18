"""
Componentes refatorados para processamento de Parquet.
Implementa Single Responsibility Principle (SRP).
"""

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
import zipfile
from typing import List, Any, Optional
from src.transform.schema_mapping import get_columns_by_filename
from src.core.interfaces import ChunkNormalizer, SkippableError, FatalError
from src.services.business_rules_service import BusinessRulesService


class ChunkNormalizerImpl:
    """Responsável APENAS por normalizar chunks de dados."""
    
    def normalize(self, df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
        """
        Garante que todas as colunas sejam strings e trata nulos
        para evitar conflitos de schema no PyArrow.
        """
        for col in columns:
            if col in df.columns:
                # Converte para string e substitui 'nan' (do pandas) por string vazia
                df[col] = df[col].astype(str).replace(['nan', 'None', 'NaN'], '')
        return df


class ZipExtractor:
    """Responsável APENAS por extrair dados de arquivos ZIP."""
    
    def __init__(self, zip_path: Path):
        self.zip_path = zip_path
    
    def extract_csv_reader(self, columns: List[str], chunk_size: int = 300000):
        """
        Extrai CSV de dentro do ZIP e retorna um pandas reader.
        
        Raises:
            FileNotFoundError: Se o ZIP não existir
            ValueError: Se não encontrar CSV dentro do ZIP
        """
        if not self.zip_path.exists():
            raise FileNotFoundError(f"ZIP file not found: {self.zip_path}")
        
        try:
            with zipfile.ZipFile(self.zip_path, 'r') as z:
                csv_files = [f for f in z.namelist() if f.endswith('.csv')]
                if not csv_files:
                    raise ValueError(f"No CSV file found in {self.zip_path}")
                
                internal_csv = csv_files[0]
                return pd.read_csv(
                    z.open(internal_csv),
                    sep=';',
                    header=None,
                    names=columns,
                    encoding='latin-1',
                    chunksize=chunk_size,
                    dtype=str,
                    low_memory=False,
                    on_bad_lines='skip'
                )
        except zipfile.BadZipFile as e:
            raise SkippableError(f"Corrupted ZIP file: {self.zip_path}") from e


class ParquetWriter:
    """Responsável APENAS por escrever arquivos Parquet."""
    
    def __init__(self, output_path: Path, schema: pa.Schema):
        self.output_path = output_path
        self.schema = schema
        self.writer = None
    
    def __enter__(self):
        self.writer = pq.ParquetWriter(
            self.output_path, 
            self.schema, 
            compression='snappy'
        )
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.writer:
            self.writer.close()
    
    def write_chunk(self, df: pd.DataFrame) -> None:
        """Escreve um chunk como tabela Parquet."""
        table = pa.Table.from_pandas(df, schema=self.schema, preserve_index=False)
        self.writer.write_table(table)


class ParquetTransformer:
    """Orquestra a transformação de ZIP para Parquet sem implementar diretamente."""
    
    def __init__(self, normalizer: ChunkNormalizer):
        self.normalizer = normalizer
    
    def process_zip(
        self, 
        zip_path: Path, 
        output_path: Path, 
        chunk_size: int = 300000,
        business_rules: Optional[BusinessRulesService] = None
    ) -> None:
        """
        Processa um arquivo ZIP completo para Parquet.
        
        Raises:
            SkippableError: Para erros que podem ser ignorados
            FatalError: Para erros que devem parar o pipeline
        """
        try:
            # Obter colunas do schema
            columns = get_columns_by_filename(zip_path.name)
            if not columns:
                raise SkippableError(f"Schema not found for {zip_path.name}")
            
            # Criar schema fixo do PyArrow
            arrow_schema = pa.schema([pa.field(col, pa.string()) for col in columns])
            
            # Extrair e processar
            extractor = ZipExtractor(zip_path)
            reader = extractor.extract_csv_reader(columns, chunk_size)
            
            with ParquetWriter(output_path, arrow_schema) as writer:
                for chunk in reader:
                    # Normalizar chunk
                    normalized_chunk = self.normalizer.normalize(chunk, columns)
                    
                    # Aplicar regras de negócio se fornecido
                    if business_rules:
                        # Categorização
                        if 'natureza_juridica' in normalized_chunk.columns and 'capital_social' in normalized_chunk.columns:
                            normalized_chunk['categoria'] = normalized_chunk.apply(
                                lambda row: business_rules.categorize_empresa(
                                    row.get('natureza_juridica', ''),
                                    float(row.get('capital_social', 0))
                                ),
                                axis=1
                            )
                        
                        # Validação de email
                        if 'email' in normalized_chunk.columns:
                            normalized_chunk['email'] = normalized_chunk['email'].apply(
                                business_rules.validate_email
                            )
                    
                    # Escrever no Parquet
                    writer.write_chunk(normalized_chunk)
                    
        except Exception as e:
            # Limpar arquivo incompleto em caso de erro
            if output_path.exists():
                try:
                    output_path.unlink()
                except:
                    pass
            
            # Classificar tipo de erro
            if isinstance(e, (FileNotFoundError, ValueError, zipfile.BadZipFile)):
                raise SkippableError(f"Skipping {zip_path.name}: {e}") from e
            else:
                raise FatalError(f"Fatal error processing {zip_path.name}: {e}") from e


class ParquetProcessor:
    """Versão refatorada que orquestra o processamento sem implementar diretamente."""
    
    def __init__(self, raw_path: Path, silver_path: Path, business_rules: Optional[BusinessRulesService] = None):
        self.raw_path = Path(raw_path)
        self.silver_path = Path(silver_path)
        self.silver_path.mkdir(parents=True, exist_ok=True)
        
        # Injetar dependências
        self.normalizer = ChunkNormalizerImpl()
        self.transformer = ParquetTransformer(self.normalizer)
        self.business_rules = business_rules
    
    def process_zip_to_parquet(self, zip_filename: str, chunk_size: int = 300000) -> None:
        """Processa um arquivo ZIP específico."""
        zip_file_path = self.raw_path / zip_filename
        output_filename = zip_filename.replace('.zip', '.parquet')
        output_path = self.silver_path / output_filename
        
        print(f"Transformando {zip_filename} -> {output_filename}...")
        
        try:
            self.transformer.process_zip(zip_file_path, output_path, chunk_size, self.business_rules)
            print(f"✅ Arquivo {output_filename} gerado com sucesso.")
        except SkippableError as e:
            print(f"⚠️ {e}")
        except FatalError as e:
            print(f"❌ {e}")
            raise
    
    def run_all(self) -> None:
        """Varre a pasta raw e processa todos os zips encontrados."""
        # Ordenar para processar arquivos menores primeiro
        zip_files = sorted(
            list(self.raw_path.glob("*.zip")), 
            key=lambda x: x.stat().st_size
        )
        
        for file in zip_files:
            # Pular se Parquet já existe e tem tamanho considerável
            output_path = self.silver_path / file.name.replace('.zip', '.parquet')
            if output_path.exists() and output_path.stat().st_size > 1024:
                print(f"⏩ Pulando {file.name} (Parquet já existe)")
                continue
            
            self.process_zip_to_parquet(file.name)
