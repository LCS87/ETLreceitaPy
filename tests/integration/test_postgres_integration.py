"""
Testes de integração com PostgreSQL.

Estes testes exigem um banco PostgreSQL populado com as tabelas
estabelecimentos, empresas, simples e municipios. Quando o banco não está
acessível (ou as tabelas não existem), os testes são pulados
automaticamente — não falham.
"""
from sqlalchemy import text, create_engine
from sqlalchemy.exc import OperationalError, ProgrammingError
import pytest


def _database_available() -> bool:
    """Verifica se o PostgreSQL está acessível com as tabelas esperadas."""
    try:
        from src.utils.env_loader import config

        url = config.DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")
        engine = create_engine(url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            # Tabelas obrigatórias
            for table in ("estabelecimentos", "empresas", "simples", "municipios"):
                conn.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
        engine.dispose()
        return True
    except (OperationalError, ProgrammingError, Exception):
        return False


DB_AVAILABLE = _database_available()


class TestDatabaseConnectivity:
    pytestmark = pytest.mark.skipif(
        not DB_AVAILABLE,
        reason="PostgreSQL indisponível ou tabelas não populadas (executar load do pipeline primeiro)",
    )

    def test_can_connect(self):
        from src.utils.env_loader import config

        url = config.DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")
        engine = create_engine(url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            assert result.scalar() == 1
        engine.dispose()

    def test_required_tables_exist(self):
        from src.utils.env_loader import config

        url = config.DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")
        engine = create_engine(url, connect_args={"connect_timeout": 3})
        with engine.connect() as conn:
            for table in ("estabelecimentos", "empresas", "simples", "municipios"):
                conn.execute(text(f"SELECT 1 FROM {table} LIMIT 1"))
        engine.dispose()


class TestQueryServiceIntegration:
    pytestmark = pytest.mark.skipif(
        not DB_AVAILABLE,
        reason="PostgreSQL indisponível ou tabelas não populadas (executar load do pipeline primeiro)",
    )

    def test_query_service_returns_rows_for_uf(self):
        from src.services.query_service import QueryService

        qs = QueryService()
        rows = list(qs.execute_query(
            table="estabelecimentos",
            columns=["cnpj_basico", "uf", "situacao_cadastral"],
            filters={"uf": "PE", "situacao_cadastral": "02"},
            limit=5,
        ))
        assert isinstance(rows, list)
        assert len(rows) <= 5
        if rows:
            assert "uf" in rows[0]

    def test_query_service_rejects_invalid_identifier(self):
        from src.services.query_service import QueryService

        qs = QueryService()
        with pytest.raises(ValueError):
            qs.execute_query(table="estabelecimentos", filters={"uf'; DROP TABLE x;--": "PE"}, limit=1)


class TestExportServiceIntegration:
    def test_export_filename_sanitization(self, tmp_path):
        from src.services.export_service import ExportService

        svc = ExportService(base_path=tmp_path)
        assert svc._validate_filename("../escape.csv") == "___escape_csv"
        with pytest.raises(ValueError):
            svc._validate_filename("")

    def test_export_filename_valid(self, tmp_path):
        from src.services.export_service import ExportService

        svc = ExportService(base_path=tmp_path)
        assert svc._validate_filename("leads_pe.csv") == "leads_pe_csv"
