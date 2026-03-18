import os
import psutil
import platform
import logging
from dotenv import load_dotenv
from pathlib import Path
from urllib.parse import quote_plus


class Config:
    def __init__(self):
        # 1. Localiza e carrega o arquivo .env
        env_path = Path(__file__).parent.parent.parent / '.env'
        load_dotenv(dotenv_path=env_path)

        # 2. HARDWARE DISCOVERY
        self.CPU_COUNT = psutil.cpu_count(logical=True)
        self.PHYSICAL_CORES = psutil.cpu_count(logical=False) or 1
        self.TOTAL_RAM_GB = psutil.virtual_memory().total / (1024 ** 3)
        self.HOSTNAME = platform.node()

        # 3. NETWORK & I/O TUNING
        self.MAX_DOWNLOADS = int(os.getenv("MAX_DOWNLOADS", 8))

        # Limpeza da URL da Receita
        raw_url = os.getenv("RECEITA_BASE_URL", "https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9")
        self.RECEITA_BASE_URL = raw_url.split("=")[-1].strip().replace('"', '').replace("'", "")

        self.HEADERS = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) ETL-Pipeline/3.0'
        }

        # 4. CPU & MEMORY TUNING (Processamento Parquet/SQL)
        self.MAX_WORKERS = int(os.getenv("MAX_WORKERS", max(self.PHYSICAL_CORES - 1, 1)))
        self.CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", 500000))
        self.POSTGRES_POOL_SIZE = int(os.getenv("POSTGRES_POOL_SIZE", 16))
        self.POSTGRES_MAX_OVERFLOW = int(os.getenv("POSTGRES_MAX_OVERFLOW", 32))

        # 5. ATRIBUTO PROFILE (Correção para o Entrypoint)
        # Define o nome do perfil baseado na capacidade detectada
        if self.TOTAL_RAM_GB > 24:
            self.PROFILE = "HIGH_RES_TUNED"
        else:
            self.PROFILE = "STANDARD_TUNED"

        # 6. DIRETÓRIOS
        self.BASE_DIR = Path(__file__).parent.parent.parent
        self.RAW_DIR = self.BASE_DIR / Path(os.getenv("RAW_DIR", "data/raw_zips"))
        self.SILVER_DIR = self.BASE_DIR / Path(os.getenv("SILVER_DIR", "data/silver_parquet"))
        self.LOG_DIR = self.BASE_DIR / Path("docs/logs")

        # 7. BANCO DE DADOS
        self.DB_USER = os.getenv("DB_USER", "admin_receita")
        self.DB_PASS = os.getenv("DB_PASS", "receita@2026")
        self.DB_HOST = os.getenv("DB_HOST", "localhost")
        self.DB_PORT = os.getenv("DB_PORT", "5432")
        self.DB_NAME = os.getenv("DB_NAME", "receita_db")

    @property
    def DATABASE_URL(self):
        password_safe = quote_plus(self.DB_PASS)
        return f"postgresql://{self.DB_USER}:{password_safe}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    def validate(self):
        for folder in [self.RAW_DIR, self.SILVER_DIR, self.LOG_DIR]:
            folder.mkdir(parents=True, exist_ok=True)
        if platform.system() == "Windows":
            os.system('chcp 65001 > nul')

        print(f"--- Hardware: {self.CPU_COUNT} Threads | {self.PHYSICAL_CORES} Cores ---")
        print(f"--- Perfil: {self.PROFILE} | Workers: {self.MAX_DOWNLOADS} Net / {self.MAX_WORKERS} CPU ---")


config = Config()