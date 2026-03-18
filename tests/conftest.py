"""
Configuração global do pytest para testes do pipeline.
Inclui fixtures compartilhadas e configuração do hypothesis.
"""
import pytest
import pandas as pd
from pathlib import Path
from hypothesis import settings, Verbosity

# Configuração do Hypothesis para property-based testing
settings.register_profile("ci", max_examples=100, deadline=None, verbosity=Verbosity.verbose)
settings.register_profile("dev", max_examples=20, deadline=None)
settings.register_profile("debug", max_examples=5, deadline=None, verbosity=Verbosity.verbose)

# Carrega perfil baseado em variável de ambiente (padrão: dev)
import os
profile = os.getenv("HYPOTHESIS_PROFILE", "dev")
settings.load_profile(profile)


# ============================================================================
# Fixtures de Dados de Teste
# ============================================================================

@pytest.fixture
def sample_phone_dataframe():
    """DataFrame de teste com dados de telefone"""
    return pd.DataFrame({
        'ddd_1': ['11', '21', '81', '85', '71', '11', '21', '81', '85', '71'],
        'telefone_1': ['987654321', '912345678', '998765432', '991234567', '987651234',
                      '87654321', '12345678', '98765432', '91234567', '87651234']
    })


@pytest.fixture
def sample_lead_record():
    """Registro de lead de teste"""
    return {
        'uf': 'PE',
        'tipo_empresa': 'LTDA',
        'operadora': 'VIVO',
        'data_inicio_atividade': '2024-01-15',
        'cnpj_completo': '12345678000190',
        'razao_social': 'EMPRESA TESTE LTDA',
        'endereco_completo': 'RUA TESTE, 123, CENTRO, PE, 50000-000',
        'email': 'contato@teste.com.br',
        'telefones': '(81) 98765-4321'
    }


@pytest.fixture
def temp_test_dir(tmp_path):
    """Diretório temporário para testes"""
    test_dir = tmp_path / "test_data"
    test_dir.mkdir()
    return test_dir


@pytest.fixture
def mock_parquet_file(temp_test_dir, sample_phone_dataframe):
    """Arquivo Parquet de teste"""
    parquet_path = temp_test_dir / "test.parquet"
    sample_phone_dataframe.to_parquet(parquet_path, compression='snappy')
    return parquet_path


# ============================================================================
# Fixtures de Configuração
# ============================================================================

@pytest.fixture
def optimization_config():
    """Configuração de otimização para testes"""
    return {
        'phone_processing': {
            'batch_size': 1000,
            'cache_enabled': True,
            'cache_max_size': 10000
        },
        'parquet_processing': {
            'chunk_size': 5000,
            'compression': 'snappy',
            'enrichment_enabled': True
        },
        'postgres_load': {
            'parallel_enabled': True,
            'max_workers': 2,
            'batch_size': 5000
        }
    }


# ============================================================================
# Fixtures de Mock para Banco de Dados
# ============================================================================

@pytest.fixture
def mock_db_engine(mocker):
    """Mock do SQLAlchemy engine para testes sem banco real"""
    mock_engine = mocker.Mock()
    mock_connection = mocker.Mock()
    mock_engine.connect.return_value.__enter__.return_value = mock_connection
    return mock_engine


# ============================================================================
# Markers Customizados
# ============================================================================

def pytest_configure(config):
    """Registra markers customizados"""
    config.addinivalue_line(
        "markers", "slow: marca testes que demoram mais de 10 segundos"
    )
    config.addinivalue_line(
        "markers", "integration: marca testes de integração que requerem serviços externos"
    )
    config.addinivalue_line(
        "markers", "benchmark: marca testes de performance/benchmark"
    )
    config.addinivalue_line(
        "markers", "property: marca property-based tests"
    )


# ============================================================================
# Hooks do Pytest
# ============================================================================

def pytest_collection_modifyitems(config, items):
    """Adiciona markers automaticamente baseado no caminho do arquivo"""
    for item in items:
        # Marca testes em tests/properties/ como property tests
        if "properties" in str(item.fspath):
            item.add_marker(pytest.mark.property)
        
        # Marca testes em tests/integration/ como integration tests
        if "integration" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        
        # Marca testes em tests/benchmarks/ como benchmark tests
        if "benchmarks" in str(item.fspath):
            item.add_marker(pytest.mark.benchmark)
