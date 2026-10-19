"""
Testes unitários para os componentes do ETLreceitaPy.
Implementa testabilidade com Dependency Injection.
"""

import asyncio
from pathlib import Path

import pytest
from unittest.mock import Mock, AsyncMock


class TestAPIEndpoints:
    """Testes para endpoints da API."""

    def test_health_check(self):
        """Teste endpoint de health check."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        client = TestClient(app)
        response = client.get("/")

        assert response.status_code == 200
        assert response.json()["status"] == "running"

    def test_list_leads_without_uf(self):
        """Teste listagem sem UF retorna erro."""
        from fastapi.testclient import TestClient
        from src.api.main import app

        client = TestClient(app)
        response = client.get("/api/v1/leads")

        # Deve retornar 422 (validação) porque UF é obrigatório
        assert response.status_code == 422


class TestBusinessRulesService:
    """Testes para BusinessRulesService."""

    def test_categorize_empresa_mei(self):
        """Teste categorização MEI: natureza 2135 + opção MEI 'S'."""
        from src.services.business_rules_service import BusinessRulesServiceImpl

        service = BusinessRulesServiceImpl()

        result = service.categorize_empresa('2135', '01', 'S')
        assert result == 'MEI'

    def test_categorize_empresa_me(self):
        """Teste categorização ME: porte '01' sem opção MEI."""
        from src.services.business_rules_service import BusinessRulesServiceImpl

        service = BusinessRulesServiceImpl()

        result = service.categorize_empresa('2135', '01', 'N')
        assert result == 'ME'

    def test_categorize_empresa_ltda(self):
        """Teste categorização LTDA: natureza 2062."""
        from src.services.business_rules_service import BusinessRulesServiceImpl

        service = BusinessRulesServiceImpl()

        result = service.categorize_empresa('2062', '03', 'N')
        assert result == 'LTDA'

    def test_categorize_empresa_epp(self):
        """Teste categorização EPP: porte '03' sem outras regras."""
        from src.services.business_rules_service import BusinessRulesServiceImpl

        service = BusinessRulesServiceImpl()

        result = service.categorize_empresa('2135', '03', 'N')
        assert result == 'EPP'

    def test_validate_email_valid(self):
        """Teste validação email válido."""
        from src.services.business_rules_service import BusinessRulesServiceImpl

        service = BusinessRulesServiceImpl()

        result = service.validate_email('empresa@exemplo.com')
        assert result == 'empresa@exemplo.com'

    def test_validate_email_contabilidade(self):
        """Teste filtragem email de contabilidade."""
        from src.services.business_rules_service import BusinessRulesServiceImpl

        service = BusinessRulesServiceImpl()

        # Emails com palavras contábeis devem ser filtrados
        assert service.validate_email('contato@contabilidade.com') is None
        assert service.validate_email('escritorio@empresa.com.br') is None
        assert service.validate_email('contador@exemplo.com') is None

    def test_validate_email_invalid_format(self):
        """Teste email com formato inválido."""
        from src.services.business_rules_service import BusinessRulesServiceImpl

        service = BusinessRulesServiceImpl()

        assert service.validate_email(None) is None
        assert service.validate_email('') is None
        assert service.validate_email('nao-e-email') is None


# Testes de integração simplificados
class TestIntegration:
    """Testes de integração entre componentes."""

    def test_full_pipeline_mock(self):
        """Teste pipeline completo com mocks."""
        # Mock das dependências (extract/load são async, transform é síncrono)
        mock_extractor = Mock()
        mock_extractor.extract = AsyncMock(return_value=[Path('file1.zip'), Path('file2.zip')])
        mock_transformer = Mock()
        mock_loader = Mock()
        mock_loader.load = AsyncMock(return_value=None)

        # Criar pipeline
        from src.config.pipeline_factory import ELTPipeline
        pipeline = ELTPipeline(mock_extractor, mock_transformer, mock_loader)

        # Executar (síncrono para teste)
        asyncio.run(pipeline.run())

        # Verificar chamadas
        mock_extractor.extract.assert_called_once()
        mock_transformer.transform.assert_called_once()
        mock_loader.load.assert_called_once()

    def test_pipeline_fatal_when_no_files(self):
        """Pipeline aborta com FatalError quando nada é extraído."""
        from src.core.interfaces import FatalError
        from src.config.pipeline_factory import ELTPipeline

        mock_extractor = Mock()
        mock_extractor.extract = AsyncMock(return_value=[])
        mock_transformer = Mock()
        mock_loader = Mock()
        mock_loader.load = AsyncMock()

        pipeline = ELTPipeline(mock_extractor, mock_transformer, mock_loader)

        with pytest.raises(FatalError):
            asyncio.run(pipeline.run())

        mock_transformer.transform.assert_not_called()
        mock_loader.load.assert_not_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
