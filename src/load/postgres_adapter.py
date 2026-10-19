import asyncio
import io
import pandas as pd
import pyarrow.parquet as pq
from sqlalchemy import create_engine, text
from pathlib import Path
from typing import Optional, Union
from src.utils.log_handler import logger
from src.utils.env_loader import config
from src.monitoring.prometheus_stats import metrics
from src.database.indexes import generate_all_index_sql


class PostgresLoader:
    def __init__(self, db_config: Optional[str] = None) -> None:
        self.url = db_config if db_config else config.DATABASE_URL
        self.engine = create_engine(
            self.url,
            connect_args={'client_encoding': 'utf8'},
            pool_size=config.POSTGRES_POOL_SIZE,
            max_overflow=config.POSTGRES_MAX_OVERFLOW
        )
        self.schema = "public"

    async def load(self) -> None:
        logger.info("--- Iniciando Carga no PostgreSQL ---")
        # Corrigido: track_duration usa apenas a label 'stage'
        with metrics.track_duration(stage="postgres_load_total"):
            await asyncio.to_thread(self.run_load_pipeline, config.SILVER_DIR)
            await asyncio.to_thread(self.create_optimization_indexes)

    def _create_table_from_df(self, df: pd.DataFrame, table_name: str) -> None:
        try:
            with metrics.track_duration(stage="create_table"):
                df.head(0).to_sql(table_name, self.engine, if_exists='append', index=False)
                logger.info(f"--- Schema da tabela '{table_name}' verificado ---")
                metrics.record_file(stage="postgres", status="table_created")
        except Exception as e:
            logger.debug(f"Aviso ao verificar schema de '{table_name}': {e}")

    def fast_load_parquet(self, parquet_path: Path, table_name: str) -> None:
        logger.info(f"--- Bulk Load: {parquet_path.name} -> {table_name} ---")

        # Corrigido: Usando record_file para garantir as labels corretas
        metrics.record_file(stage="postgres", status="attempt")

        with metrics.track_duration(stage="postgres_load_file"):
            try:
                parquet_file = pq.ParquetFile(parquet_path)
                num_groups = parquet_file.num_row_groups
                total_rows = 0

                for i in range(num_groups):
                    logger.info(f"Lote {i + 1}/{num_groups} de {parquet_path.name}...")

                    with metrics.track_duration(stage="postgres_load_batch"):
                        df = parquet_file.read_row_group(i).to_pandas()
                        batch_rows = len(df)
                        total_rows += batch_rows

                        df = df.fillna('')
                        # Limpeza de caracteres que quebram o COPY
                        for col in df.select_dtypes(include=['object']).columns:
                            df[col] = df[col].astype(str).str.replace(r'\\', '', regex=True)

                        if i == 0:
                            self._create_table_from_df(df, table_name)

                        self._execute_copy(df, table_name)

                        # ATUALIZA O GRÁFICO DE LINHAS/SEG NO GRAFANA
                        metrics.record_rows(table_name=table_name, count=batch_rows)

                metrics.record_file(stage="postgres", status="success")
                logger.info(f" {parquet_path.name} carregado: {total_rows} linhas")

            except Exception as e:
                logger.error(f"Erro ao processar {parquet_path.name}: {e}")
                metrics.record_file(stage="postgres", status="error")
                raise e

    def _execute_copy(self, df: pd.DataFrame, table_name: str) -> None:
        # Obtemos a conexão bruta do engine
        raw_conn = self.engine.raw_connection()
        try:
            # Em algumas versões do SQLAlchemy, usamos .driver_connection para o psycopg2
            # Se não existir, usamos a raw_conn diretamente
            connection = getattr(raw_conn, 'driver_connection', raw_conn)
            cursor = connection.cursor()

            try:
                # 1. PEGAR AS COLUNAS REAIS DA TABELA
                cursor.execute(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = %s ORDER BY ordinal_position",
                    (table_name.lower(),)
                )
                db_columns = [row[0] for row in cursor.fetchall()]

                if not db_columns:
                    logger.warning(f"⚠ Tabela {table_name} não encontrada no banco.")
                    return

                # 2. FILTRAR O DATAFRAME
                cols_to_use = [c for c in db_columns if c in df.columns]
                df_to_copy = df[cols_to_use].copy()

                # 3. PREPARAR O BUFFER (StringIO)
                output = io.StringIO()
                df_to_copy.to_csv(output, sep='\t', header=False, index=False, quoting=1)
                output.seek(0)

                # 4. EXECUTAR O COPY (Rápido)
                columns_str = ', '.join([f'"{c}"' for c in cols_to_use])
                sql = f"COPY {table_name} ({columns_str}) FROM STDIN WITH CSV DELIMITER '\t' QUOTE '\"'"

                cursor.copy_expert(sql, output)
                connection.commit()
                # logger.info(f" {table_name}: {len(df_to_copy)} linhas inseridas.")

            except Exception as e:
                connection.rollback()
                logger.error(f" Erro no processamento do COPY {table_name}: {e}")
                raise e
            finally:
                cursor.close()

        finally:
            # IMPORTANTE: Fechar a raw_connection para devolver ao pool do SQLAlchemy
            raw_conn.close()

    def run_load_pipeline(self, silver_path: Union[str, Path]) -> None:
        p = Path(silver_path)
        parquet_files = sorted([f for f in p.glob("*.parquet") if f.is_file()])
        logger.info(f"Encontrados {len(parquet_files)} arquivos Parquet para carga")

        # Tabelas principais que serão recarregadas
        MAIN_TABLES = ['estabelecimentos', 'empresas', 'socios', 'simples',
                       'cnaes', 'municipios', 'naturezas', 'paises', 'qualificacoes', 'motivos']

        # TRUNCATE antes de carregar para evitar duplicatas em re-execucoes
        logger.info("Limpando tabelas antes da carga (evita duplicatas)...")
        with self.engine.connect() as conn:
            for table in MAIN_TABLES:
                try:
                    conn.execute(text(f"TRUNCATE TABLE {table} RESTART IDENTITY CASCADE;"))
                    conn.commit()
                    logger.info(f"Tabela {table} limpa.")
                except Exception:
                    conn.rollback()  # Tabela pode não existir ainda na primeira execucao

        for file in parquet_files:
            if "exports" in str(file).lower():
                metrics.record_file(stage="postgres", status="skipped")
                continue

            stem_clean = "".join([i for i in file.stem if not i.isdigit()]).lower()
            table_name = "estabelecimentos" if "estabelecimentos" in stem_clean else \
                "leads_nordeste" if "leads" in stem_clean else stem_clean

            self.fast_load_parquet(file, table_name)

    def create_optimization_indexes(self) -> None:
        logger.info("--- Criando Índices de Performance ---")
        with metrics.track_duration(stage="postgres_indexes"):
            with self.engine.connect() as conn:
                for sql in generate_all_index_sql():
                    with metrics.track_duration(stage="postgres_create_index"):
                        try:
                            conn.execute(text(sql))
                            conn.commit()
                            metrics.record_file(stage="postgres_index", status="created")
                        except Exception as e:
                            logger.warning(f"Aviso no índice: {e}")
                            metrics.record_file(stage="postgres_index", status="error")