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
    """Responsável por normalizar chunks de dados."""

    def normalize(self, df: pd.DataFrame, columns: List[str]) -> pd.DataFrame:
        for col in columns:
            if col in df.columns:
                df[col] = df[col].astype(str).replace(['nan', 'None', 'NaN', 'nan'], '')
        return df


class ZipExtractor:
    """Responsável por extrair dados de arquivos ZIP."""

    def __init__(self, zip_path: Path):
        self.zip_path = zip_path

    def extract_csv_reader(self, columns: List[str], chunk_size: int = 300000):
        if not self.zip_path.exists():
            raise FileNotFoundError(f"ZIP não encontrado: {self.zip_path}")

        try:
            z = zipfile.ZipFile(self.zip_path, 'r')
            csv_files = [f for f in z.namelist() if f.endswith('.csv') or '.csv' in f]
            if not csv_files:
                internal_file = z.namelist()[0]  # Pega o primeiro arquivo se não tiver extensão .csv
            else:
                internal_file = csv_files[0]

            return pd.read_csv(
                z.open(internal_file),
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
            raise SkippableError(f"ZIP corrompido: {self.zip_path}") from e


class ParquetWriter:
    """Responsável por escrever arquivos Parquet."""

    def __init__(self, output_path: Path, schema: pa.Schema):
        self.output_path = output_path
        self.schema = schema
        self.writer = None

    def __enter__(self):
        self.writer = pq.ParquetWriter(self.output_path, self.schema, compression='snappy')
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.writer:
            self.writer.close()

    def write_chunk(self, df: pd.DataFrame) -> None:
        table = pa.Table.from_pandas(df, schema=self.schema, preserve_index=False)
        self.writer.write_table(table)


class ParquetTransformer:
    """Orquestra a transformação de ZIP para Parquet."""

    def __init__(self, normalizer: ChunkNormalizer):
        self.normalizer = normalizer

    def process_zip(self, zip_path: Path, output_path: Path, columns: List[str]) -> None:
        arrow_schema = pa.schema([pa.field(col, pa.string()) for col in columns])
        extractor = ZipExtractor(zip_path)
        reader = extractor.extract_csv_reader(columns)

        with ParquetWriter(output_path, arrow_schema) as writer:
            for chunk in reader:
                normalized_chunk = self.normalizer.normalize(chunk, columns)
                writer.write_chunk(normalized_chunk)


class ParquetProcessor:
    """Classe principal que o Pipeline chama via .transform()"""

    def __init__(self, raw_path: Path, silver_path: Path, business_rules: Optional[Any] = None):
        self.raw_path = Path(raw_path)
        self.silver_path = Path(silver_path)
        self.silver_path.mkdir(parents=True, exist_ok=True)
        self.normalizer = ChunkNormalizerImpl()
        self.processor = ParquetTransformer(self.normalizer)

    def transform(self, files: List[Path]) -> None:
        """MÉTODO PRINCIPAL EXIGIDO PELA INTERFACE"""
        for file_path in files:
            output_path = self.silver_path / file_path.name.replace('.zip', '.parquet')

            if output_path.exists() and output_path.stat().st_size > 1024:
                print(f" Pulando {file_path.name} (Parquet já existe)")
                continue

            print(f"Transformando {file_path.name} -> {output_path.name}...")

            columns = get_columns_by_filename(file_path.name)
            if not columns:
                print(f"️ Schema não encontrado para {file_path.name}. Pulando...")
                continue

            try:
                self.processor.process_zip(file_path, output_path, columns)
                print(f" Arquivo {output_path.name} gerado com sucesso.")
            except Exception as e:
                print(f" Erro em {file_path.name}: {e}")
                if output_path.exists(): output_path.unlink()