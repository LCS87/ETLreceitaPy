"""Testes de segurança para QueryService."""

import pytest
from unittest.mock import MagicMock
from src.services.query_service import QueryService


class TestQueryServiceSecurity:
    """Testes de segurança para QueryService."""

    def setup_method(self):
        self.engine = MagicMock()
        self.service = QueryService(self.engine)

    def test_sql_injection_in_table_name(self):
        """Testa que SQL Injection no nome da tabela é bloqueado."""
        with pytest.raises(ValueError, match="Tabela nao permitida"):
            self.service.build_select_query(
                "estabelecimentos; DROP TABLE users; --",
                ["cnpj_basico"]
            )

    def test_sql_injection_in_column_name(self):
        """Testa que SQL Injection no nome da coluna é bloqueado."""
        with pytest.raises(ValueError, match="Colunas nao permitidas"):
            self.service.build_select_query(
                "estabelecimentos",
                ["cnpj_basico; DROP TABLE users; --"]
            )

    def test_sql_injection_in_filter_field(self):
        """Testa que SQL Injection no campo de filtro é bloqueado."""
        with pytest.raises(ValueError, match="Coluna de filtro nao permitida"):
            self.service.build_select_query(
                "estabelecimentos",
                ["cnpj_basico"],
                {"uf; DROP TABLE users; --": "SP"}
            )

    def test_sql_injection_in_filter_value(self):
        """Testa que SQL Injection no valor do filtro é parametrizado."""
        query, params = self.service.build_select_query(
            "estabelecimentos",
            ["cnpj_basico"],
            {"uf": "SP'; DROP TABLE users; --"}
        )
        # O valor deve ser parametrizado, não interpolado diretamente
        assert ":filter_0" in query.text
        assert params["filter_0"] == "SP'; DROP TABLE users; --"

    def test_valid_table_and_columns(self):
        """Testa que tabela e colunas válidas funcionam corretamente."""
        query, params = self.service.build_select_query(
            "estabelecimentos",
            ["cnpj_basico", "nome_fantasia"],
            {"uf": "SP", "situacao_cadastral": "02"}
        )
        assert "SELECT" in query.text
        assert "FROM estabelecimentos" in query.text
        assert "uf" in query.text
        assert "situacao_cadastral" in query.text

    def test_filter_with_list_values(self):
        """Testa que filtros com lista de valores são parametrizados."""
        query, params = self.service.build_select_query(
            "estabelecimentos",
            ["cnpj_basico"],
            {"uf": ["SP", "RJ", "MG"]}
        )
        assert "IN" in query.text
        assert "filter_0_0" in params
        assert "filter_0_1" in params
        assert "filter_0_2" in params

    def test_filter_with_ilike(self):
        """Testa que filtros com % usam ILIKE."""
        query, params = self.service.build_select_query(
            "estabelecimentos",
            ["cnpj_basico"],
            {"nome_fantasia": "%restaurante%"}
        )
        assert "ILIKE" in query.text
        assert params["filter_0"] == "%restaurante%"

    def test_limit_validation(self):
        """Testa que o limit é validado e limitado."""
        query, params = self.service.build_select_query(
            "estabelecimentos",
            ["cnpj_basico"],
            limit=999999999
        )
        assert params["query_limit"] == 1_000_000

    def test_empty_columns_raises_error(self):
        """Testa que colunas vazias geram erro."""
        with pytest.raises(ValueError, match="Selecione ao menos uma coluna"):
            self.service.build_select_query("estabelecimentos", [])

    def test_validate_identifier_valid(self):
        """Testa identificadores válidos."""
        assert self.service._validate_identifier("cnpj_basico") is True
        assert self.service._validate_identifier("_test") is True
        assert self.service._validate_identifier("col123") is True

    def test_validate_identifier_invalid(self):
        """Testa identificadores inválidos."""
        assert self.service._validate_identifier("123col") is False
        assert self.service._validate_identifier("col;DROP") is False
        assert self.service._validate_identifier("col--") is False
        assert self.service._validate_identifier("") is False
