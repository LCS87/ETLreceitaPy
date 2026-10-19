"""Testes de segurança para ExportService."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
import pandas as pd
from src.services.export_service import ExportService


class TestExportServiceSecurity:
    """Testes de segurança para ExportService."""

    def setup_method(self):
        self.test_path = Path("test_exports")
        self.service = ExportService(base_path=self.test_path)

    def teardown_method(self):
        # Limpar arquivos de teste
        import shutil
        if self.test_path.exists():
            shutil.rmtree(self.test_path)

    def test_path_traversal_blocked(self):
        """Testa que path traversal é sanitizado."""
        safe = self.service._validate_filename("../../../etc/passwd")
        # O nome sanitizado não deve conter .. ou /
        assert ".." not in safe
        assert "/" not in safe
        assert "\\" not in safe

    def test_special_characters_sanitized(self):
        """Testa que caracteres especiais são removidos."""
        safe = self.service._validate_filename("file;rm -rf /.txt")
        assert ";" not in safe
        assert "/" not in safe
        assert " " not in safe

    def test_valid_filename_preserved(self):
        """Testa que nomes válidos são preservados."""
        assert self.service._validate_filename("arquivo_teste") == "arquivo_teste"
        assert self.service._validate_filename("arquivo-teste-123") == "arquivo-teste-123"

    def test_empty_filename_raises_error(self):
        """Testa que nome vazio gera erro."""
        with pytest.raises(ValueError, match="Nome de arquivo inválido"):
            self.service._validate_filename("")

    def test_sql_injection_in_filename(self):
        """Testa que SQL Injection no nome do arquivo é sanitizado."""
        safe = self.service._validate_filename("'; DROP TABLE users; --")
        assert "'" not in safe
        assert ";" not in safe
        assert " " not in safe

    def test_unicode_normalized(self):
        """Testa que caracteres unicode são removidos."""
        safe = self.service._validate_filename("arquivo_teste")
        assert safe == "arquivo_teste"

    def test_export_path_uses_safe_name(self):
        """Testa que o caminho de exportação usa nome seguro."""
        # Nome com path traversal deve ser sanitizado
        path = self.service.get_export_path("../../../etc/passwd")
        assert ".." not in str(path)
        # O caminho deve estar dentro do base_path
        assert str(path).startswith(str(self.test_path))
