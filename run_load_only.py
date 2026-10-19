"""Executa somente a carga dos Parquets no PostgreSQL."""

from src.load.postgres_adapter import PostgresLoader
from src.utils.env_loader import config


if __name__ == "__main__":
    config.validate()
    loader = PostgresLoader(db_config=config.DATABASE_URL)
    loader.run_load_pipeline(silver_path=config.SILVER_DIR)
    loader.create_optimization_indexes()
