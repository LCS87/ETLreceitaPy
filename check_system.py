import os
import socket
import psycopg2
import pandas as pd
from pathlib import Path
from src.utils.env_loader import config
from src.utils.log_handler import logger


def check_disk_access():
    print(" [1/4] Verificando acesso ao Disco D:...")
    try:
        config.validate()
        test_file = config.RAW_DIR / "test_write.tmp"
        test_file.write_text("teste")
        test_file.unlink()
        print("    Permissão de escrita OK!")
    except Exception as e:
        print(f"    ERRO de Disco: {e}")


def check_postgres():
    print(f"🐘 [2/4] Verificando PostgreSQL ({config.DB_HOST})...")
    try:
        conn = psycopg2.connect(
            host=config.DB_HOST,
            database=config.DB_NAME,
            user=config.DB_USER,
            password=config.DB_PASS,
            port=config.DB_PORT,
            connect_timeout=3
        )
        conn.close()
        print("    Conexão com Banco de Dados OK!")
    except Exception as e:
        print(f"    ERRO de Banco: {e}")
        print("      DICA: Verifique se o Docker está rodando e se a senha 'receita@2026' está correta.")


def check_ports():
    print("📡 [3/4] Verificando portas de Monitoramento...")
    for service, port in [("Prometheus", 8000), ("Grafana", 3000)]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            result = s.connect_ex(('localhost', port))
            status = "OK" if result != 0 else "OCUPADA (Ativa)"
            print(f"   ℹ Porta {port} ({service}): {status}")


def check_dependencies():
    print(" [4/4] Verificando Bibliotecas Críticas...")
    deps = ['pandas', 'sqlalchemy', 'phonenumbers', 'psutil', 'dotenv']
    missing = []
    for d in deps:
        try:
            __import__(d)
        except ImportError:
            missing.append(d)

    if not missing:
        print("    Todas as bibliotecas estão instaladas!")
    else:
        print(f"    FALTANDO: {', '.join(missing)}")
        print("      Rode: pip install -r requirements.txt")


if __name__ == "__main__":
    print("=" * 50)
    print("🔍 DIAGNÓSTICO PRÉ-DECOLAGEM - ETL RECEITA")
    print("=" * 50)
    check_disk_access()
    print("-" * 30)
    check_postgres()
    print("-" * 30)
    check_ports()
    print("-" * 30)
    check_dependencies()
    print("=" * 50)
    print(" Se tudo estiver verde, execute: python app_entrypoint.py")