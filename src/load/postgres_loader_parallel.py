"""
Loader PostgreSQL com processamento paralelo.
Carrega múltiplos arquivos Parquet simultaneamente usando multiprocessing.
"""
import os
import io
import pandas as pd
import pyarrow.parquet as pq
from sqlalchemy import create_engine, text, Engine
from pathlib import Path
from typing import List, Dict
from concurrent.futures import ProcessPoolExecutor, as_completed

from src.utils.log_handler import logger
from src.utils.env_loader import config
from src.monitoring.prometheus_stats import metrics


class PostgresLoaderParallel:
    """Loader com processamento paralelo de arquivos"""
    
    def __init__(self, db_config: str = None, max_workers: int = None) -> None:
        self.db_config = db_config or config.DATABASE_URL
        self.max_workers = max_workers or max(os.cpu_count() - 1, 1)
        self.engine = create_engine(
            self.db_config,
            connect_args={'client_encoding': 'utf8'},
            pool_size=20,
            max_overflow=40
        )
    
    async def load(self, silver_path: Path = None) -> None:
        """Carrega arquivos Parquet em paralelo"""
        logger.info("--- Iniciando Carga Paralela no PostgreSQL ---")
        with metrics.track_duration(stage="postgres_load_total"):
            self.run_load_pipeline(silver_path or config.SILVER_DIR)
            self.create_optimization_indexes()
    
    def run_load_pipeline(self, silver_path: Path) -> None:
        """Distribui arquivos entre workers"""
        from src.monitoring.prometheus_stats import metrics
        
        p = Path(silver_path)
        parquet_files = sorted([f for f in p.glob("*.parquet") if f.is_file()])
        parquet_files = [f for f in parquet_files if "exports" not in str(f).lower()]
        
        logger.info(f"Encontrados {len(parquet_files)} arquivos para carga paralela")
        logger.info(f"Usando {self.max_workers} workers")
        
        # Registra número de workers (Task 9.2)
        metrics.record_parallel_workers(self.max_workers)
        
        with ProcessPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {executor.submit(self._load_single_file_static, 
                                      str(file), self.db_config): file 
                      for file in parquet_files}
            
            completed = 0
            for future in as_completed(futures):
                file = futures[future]
                try:
                    result = future.result()
                    completed += 1
                    logger.info(f"Progresso: {completed}/{len(parquet_files)} arquivos")
                except Exception as e:
                    logger.error(f"Erro em {file.name}: {e}")
    
    @staticmethod
    def _load_single_file_static(file_path_str: str, db_config: str) -> Dict:
        """Worker estático para processar um arquivo"""
        from sqlalchemy import create_engine
        import pyarrow.parquet as pq
        
        file_path = Path(file_path_str)
        engine = create_engine(db_config)
        
        stem_clean = "".join([i for i in file_path.stem if not i.isdigit()]).lower()
        table_name = "estabelecimentos" if "estabelecimentos" in stem_clean else stem_clean
        
        parquet_file = pq.ParquetFile(file_path)
        total_rows = 0
        
        for i in range(parquet_file.num_row_groups):
            df = parquet_file.read_row_group(i).to_pandas()
            df = df.fillna('')
            
            if i == 0:
                df.head(0).to_sql(table_name, engine, if_exists='append', index=False)
            
            PostgresLoaderParallel._execute_copy_static(df, table_name, engine)
            total_rows += len(df)
        
        return {'file': file_path.name, 'rows': total_rows}

    @staticmethod
    def _execute_copy_static(df: pd.DataFrame, table_name: str, engine: Engine) -> None:
        """Executa COPY command"""
        raw_conn = engine.raw_connection()
        try:
            connection = getattr(raw_conn, 'driver_connection', raw_conn)
            cursor = connection.cursor()
            
            cursor.execute(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name = '{table_name.lower()}' ORDER BY ordinal_position"
            )
            db_columns = [row[0] for row in cursor.fetchall()]
            
            if db_columns:
                cols_to_use = [c for c in db_columns if c in df.columns]
                df_to_copy = df[cols_to_use].copy()
                
                output = io.StringIO()
                df_to_copy.to_csv(output, sep='\t', header=False, index=False, quoting=1)
                output.seek(0)
                
                columns_str = ', '.join([f'"{c}"' for c in cols_to_use])
                sql = f"COPY {table_name} ({columns_str}) FROM STDIN WITH CSV DELIMITER '\t' QUOTE '\"'"
                
                cursor.copy_expert(sql, output)
                connection.commit()
            
            cursor.close()
        finally:
            raw_conn.close()
    
    def create_optimization_indexes(self) -> None:
        """Cria índices após carga"""
        logger.info("--- Criando Índices de Performance ---")
        with metrics.track_duration(stage="postgres_indexes"):
            with open('src/database/create_indexes.sql', 'r') as f:
                sql_script = f.read()
            
            with self.engine.connect() as conn:
                for statement in sql_script.split(';'):
                    if statement.strip():
                        try:
                            conn.execute(text(statement))
                            conn.commit()
                        except Exception as e:
                            logger.warning(f"Aviso no índice: {e}")
