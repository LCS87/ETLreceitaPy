"""
Testes unitários para os componentes refatorados do ETLreceitaPy.
Implementa testabilidade com Dependency Injection.
"""

import pytest
import pandas as pd
import pyarrow as pa
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import zipfile
import tempfile
import os

# Importar componentes refatorados
from src.core.interfaces import ChunkNormalizer, SkippableError, FatalError
from src.transform.parquet_engine_refactored import (
    ChunkNormalizerImpl, 
    ZipExtractor, 
    ParquetWriter, 
    ParquetTransformer,
    ParquetProcessor
)


class TestChunkNormalizer:
    """Testes para ChunkNormalizer."""
    
    def test_normalize_basic(self):
        """Teste básico de normalização."""
        normalizer = ChunkNormalizerImpl()
        
        df = pd.DataFrame({
            'col1': ['nan', 'valor', 'None', 'NaN', ''],
            'col2': [1, 2, 3, 4, 5],
            'col3': ['texto', 'nan', 'None', 'outro', 'NaN']
        })
        
        result = normalizer.normalize(df, ['col1', 'col3'])
        
        # Verificar que nulos foram substituídos por string vazia
        assert result['col1'].tolist() == ['', 'valor', '', '', '']
        assert result['col3'].tolist() == ['texto', '', '', 'outro', '']
        # Coluna não processada deve permanecer igual
        assert result['col2'].tolist() == [1, 2, 3, 4, 5]
    
    def test_normalize_empty_dataframe(self):
        """Teste normalização de DataFrame vazio."""
        normalizer = ChunkNormalizerImpl()
        
        df = pd.DataFrame()
        result = normalizer.normalize(df, ['col1'])
        
        assert result.empty
    
    def test_normalize_nonexistent_columns(self):
        """Teste normalização com colunas que não existem."""
        normalizer = ChunkNormalizerImpl()
        
        df = pd.DataFrame({'col1': ['a', 'b']})
        result = normalizer.normalize(df, ['col1', 'col2'])
        
        # Deve processar apenas colunas existentes
        assert result['col1'].tolist() == ['a', 'b']
        assert 'col2' not in result.columns


class TestZipExtractor:
    """Testes para ZipExtractor."""
    
    def test_extractor_with_valid_zip(self):
        """Teste extração com ZIP válido."""
        # Criar ZIP temporário para teste
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_zip:
            with zipfile.ZipFile(tmp_zip.name, 'w') as zf:
                zf.writestr('test.csv', 'col1;col2\nval1;val2\nval3;val4')
            
            extractor = ZipExtractor(Path(tmp_zip.name))
            reader = extractor.extract_csv_reader(['col1', 'col2'], chunksize=2)
            
            # Ler primeiro chunk
            chunk = next(reader)
            assert chunk['col1'].tolist() == ['val1', 'val2']
            assert chunk['col2'].tolist() == ['val3', 'val4']
            
            # Limpar
            os.unlink(tmp_zip.name)
    
    def test_extractor_nonexistent_file(self):
        """Teste extração com arquivo inexistente."""
        extractor = ZipExtractor(Path('nonexistent.zip'))
        
        with pytest.raises(FileNotFoundError):
            extractor.extract_csv_reader(['col1'])
    
    def test_extractor_corrupted_zip(self):
        """Teste extração com ZIP corrompido."""
        # Criar arquivo corrompido
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_zip:
            tmp_zip.write(b'not a zip file')
            
            extractor = ZipExtractor(Path(tmp_zip.name))
            
            with pytest.raises(SkippableError):
                extractor.extract_csv_reader(['col1'])
            
            os.unlink(tmp_zip.name)
    
    def test_extractor_no_csv_inside(self):
        """Teste ZIP sem CSV interno."""
        with tempfile.NamedTemporaryFile(suffix='.zip', delete=False) as tmp_zip:
            with zipfile.ZipFile(tmp_zip.name, 'w') as zf:
                zf.writestr('test.txt', 'not a csv')
            
            extractor = ZipExtractor(Path(tmp_zip.name))
            
            with pytest.raises(SkippableError):
                extractor.extract_csv_reader(['col1'])
            
            os.unlink(tmp_zip.name)


class TestParquetWriter:
    """Testes para ParquetWriter."""
    
    def test_writer_context_manager(self):
        """Teste writer como context manager."""
        with tempfile.NamedTemporaryFile(suffix='.parquet', delete=False) as tmp_file:
            output_path = Path(tmp_file.name)
            
            schema = pa.schema([
                pa.field('col1', pa.string()),
                pa.field('col2', pa.string())
            ])
            
            df = pd.DataFrame({
                'col1': ['val1', 'val2'],
                'col2': ['val3', 'val4']
            })
            
            with ParquetWriter(output_path, schema) as writer:
                writer.write_chunk(df)
            
            # Verificar que arquivo foi criado
            assert output_path.exists()
            assert output_path.stat().st_size > 0
            
            # Ler e verificar conteúdo
            table = pq.read_table(output_path)
            assert table.num_rows == 2
            assert table.column_names == ['col1', 'col2']
            
            os.unlink(output_path)


class TestParquetTransformer:
    """Testes para ParquetTransformer."""
    
    def test_transformer_success(self):
        """Teste transformação bem-sucedida."""
        # Mock normalizer
        mock_normalizer = Mock(spec=ChunkNormalizer)
        mock_normalizer.normalize.return_value = pd.DataFrame({'col1': ['val1']})
        
        # Mock extractor e writer
        with patch('src.transform.parquet_engine_refactored.ZipExtractor') as mock_extractor_class, \
             patch('src.transform.parquet_engine_refactored.ParquetWriter') as mock_writer_class:
            
            # Configurar mocks
            mock_extractor = Mock()
            mock_reader = Mock()
            mock_reader.__iter__ = Mock(return_value=iter([pd.DataFrame({'col1': ['val1']})]))
            mock_extractor.extract_csv_reader.return_value = mock_reader
            mock_extractor_class.return_value = mock_extractor
            
            mock_writer = Mock()
            mock_writer.__enter__ = Mock(return_value=mock_writer)
            mock_writer.__exit__ = Mock(return_value=None)
            mock_writer_class.return_value = mock_writer
            
            # Mock schema mapping
            with patch('src.transform.parquet_engine_refactored.get_columns_by_filename') as mock_schema:
                mock_schema.return_value = ['col1']
                
                transformer = ParquetTransformer(mock_normalizer)
                
                # Executar transformação
                transformer.process_zip(
                    Path('test.zip'),
                    Path('output.parquet')
                )
                
                # Verificar chamadas
                mock_normalizer.normalize.assert_called_once()
                mock_writer.write_chunk.assert_called_once()
    
    def test_transformer_skippable_error(self):
        """Teste transformação com erro skippable."""
        mock_normalizer = Mock(spec=ChunkNormalizer)
        
        with patch('src.transform.parquet_engine_refactored.ZipExtractor') as mock_extractor_class:
            mock_extractor = Mock()
            mock_extractor.extract_csv_reader.side_effect = FileNotFoundError("File not found")
            mock_extractor_class.return_value = mock_extractor
            
            with patch('src.transform.parquet_engine_refactored.get_columns_by_filename') as mock_schema:
                mock_schema.return_value = ['col1']
                
                transformer = ParquetTransformer(mock_normalizer)
                
                with pytest.raises(SkippableError):
                    transformer.process_zip(Path('test.zip'), Path('output.parquet'))


class TestParquetProcessor:
    """Testes para ParquetProcessor."""
    
    def test_processor_initialization(self):
        """Teste inicialização do processor."""
        from src.transform.parquet_engine_refactored import ParquetProcessor
        
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "raw"
            silver_path = Path(temp_dir) / "silver"
            
            raw_path.mkdir()
            
            processor = ParquetProcessor(raw_path, silver_path)
            
            assert processor.raw_path == raw_path
            assert processor.silver_path == silver_path
            assert silver_path.exists()
    
    def test_processor_with_business_rules(self):
        """Teste processor com business rules injetado."""
        from src.transform.parquet_engine_refactored import ParquetProcessor
        from src.services.business_rules_service import BusinessRulesServiceImpl
        
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "raw"
            silver_path = Path(temp_dir) / "silver"
            
            raw_path.mkdir()
            
            business_rules = BusinessRulesServiceImpl()
            processor = ParquetProcessor(raw_path, silver_path, business_rules)
            
            assert processor.business_rules == business_rules


class TestParquetWriter:
    """Testes para ParquetWriter."""
    
    def test_write_parquet_basic(self, sample_dataframe):
        """Teste escrita básica de Parquet."""
        from src.transform.parquet_engine_refactored import ParquetWriter
        
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "test.parquet"
            
            schema = pa.schema([
                pa.field('col1', pa.string()),
                pa.field('col2', pa.int64())
            ])
            
            with ParquetWriter(output_path, schema) as writer:
                writer.write_chunk(sample_dataframe)
            
            # Verificar
            assert output_path.exists()
            pf = pq.ParquetFile(output_path)
            assert pf.num_row_groups == 1


class TestParquetTransformer:
    """Testes para ParquetTransformer."""
    
    def test_transformer_process_zip(self, sample_dataframe):
        """Teste transformação completa ZIP -> Parquet."""
        from src.transform.parquet_engine_refactored import ParquetTransformer, ChunkNormalizerImpl
        
        normalizer = ChunkNormalizerImpl()
        transformer = ParquetTransformer(normalizer)
        
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_dir = Path(temp_dir)
            
            # Criar ZIP de teste
            zip_path = temp_dir / "test.zip"
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('test.csv', 'col1;col2\nnan;valor\nNone;123')
            
            output_path = temp_dir / "output.parquet"
            
            # Mockar get_columns_by_filename
            with patch('src.transform.parquet_engine_refactored.get_columns_by_filename') as mock_cols:
                mock_cols.return_value = ['col1', 'col2']
                
                # Executar transformação
                transformer.process_zip(zip_path, output_path)
            
            # Verificar resultado
            assert output_path.exists()
            df = pd.read_parquet(output_path)
            assert len(df) == 2
            assert df['col1'].tolist() == ['', '']  # Normalizadas


class TestAPIEndpoints:
    """Testes para endpoints da API."""
    
    @pytest.mark.asyncio
    async def test_health_check(self):
        """Teste endpoint de health check."""
        from fastapi.testclient import TestClient
        from src.api.main import app
        
        client = TestClient(app)
        response = client.get("/")
        
        assert response.status_code == 200
        assert response.json()["status"] == "running"
    
    @pytest.mark.asyncio
    async def test_list_leads_without_uf(self):
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
        """Teste categorização MEI."""
        from src.services.business_rules_service import BusinessRulesServiceImpl
        
        service = BusinessRulesServiceImpl()
        
        # Natureza 2135 com capital <= 81k = MEI
        result = service.categorize_empresa('2135', 50000)
        assert result == 'MEI'
    
    def test_categorize_empresa_me(self):
        """Teste categorização ME."""
        from src.services.business_rules_service import BusinessRulesServiceImpl
        
        service = BusinessRulesServiceImpl()
        
        # Natureza 2135 com capital > 81k = ME
        result = service.categorize_empresa('2135', 100000)
        assert result == 'ME'
    
    def test_categorize_empresa_ltda(self):
        """Teste categorização LTDA."""
        from src.services.business_rules_service import BusinessRulesServiceImpl
        
        service = BusinessRulesServiceImpl()
        
        # Natureza 2062 = LTDA
        result = service.categorize_empresa('2062', 100000)
        assert result == 'LTDA'
    
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
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "raw"
            silver_path = Path(temp_dir) / "silver"
            
            raw_path.mkdir()
            
            processor = ParquetProcessor(raw_path, silver_path)
            
            assert processor.raw_path == raw_path
            assert processor.silver_path == silver_path
            assert silver_path.exists()
            assert isinstance(processor.normalizer, ChunkNormalizerImpl)
            assert isinstance(processor.transformer, ParquetTransformer)
    
    def test_process_zip_to_parquet_success(self):
        """Teste processamento de ZIP para Parquet com sucesso."""
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "raw"
            silver_path = Path(temp_dir) / "silver"
            
            raw_path.mkdir()
            
            # Criar ZIP de teste
            zip_path = raw_path / "test.zip"
            with zipfile.ZipFile(zip_path, 'w') as zf:
                zf.writestr('test.csv', 'col1;col2\nval1;val2\n')
            
            processor = ParquetProcessor(raw_path, silver_path)
            
            # Mock transformer para evitar dependências externas
            processor.transformer = Mock()
            processor.transformer.process_zip.return_value = None
            
            # Executar
            processor.process_zip_to_parquet("test.zip")
            
            # Verificar que método foi chamado
            processor.transformer.process_zip.assert_called_once()
    
    def test_process_zip_to_parquet_skippable_error(self):
        """Teste processamento com erro skippable."""
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "raw"
            silver_path = Path(temp_dir) / "silver"
            
            raw_path.mkdir()
            
            processor = ParquetProcessor(raw_path, silver_path)
            
            # Mock transformer para levantar SkippableError
            processor.transformer = Mock()
            processor.transformer.process_zip.side_effect = SkippableError("Test error")
            
            # Executar - não deve levantar exceção
            processor.process_zip_to_parquet("test.zip")
    
    def test_process_zip_to_parquet_fatal_error(self):
        """Teste processamento com erro fatal."""
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "raw"
            silver_path = Path(temp_dir) / "silver"
            
            raw_path.mkdir()
            
            processor = ParquetProcessor(raw_path, silver_path)
            
            # Mock transformer para levantar FatalError
            processor.transformer = Mock()
            processor.transformer.process_zip.side_effect = FatalError("Fatal error")
            
            # Executar - deve levantar exceção
            with pytest.raises(FatalError):
                processor.process_zip_to_parquet("test.zip")
    
    def test_run_all_skip_existing(self):
        """Teste run_all pulando arquivos existentes."""
        with tempfile.TemporaryDirectory() as temp_dir:
            raw_path = Path(temp_dir) / "raw"
            silver_path = Path(temp_dir) / "silver"
            
            raw_path.mkdir()
            silver_path.mkdir()
            
            # Criar ZIP e Parquet existente
            zip_path = raw_path / "test.zip"
            parquet_path = silver_path / "test.parquet"
            
            zip_path.write_text("dummy")
            parquet_path.write_text("dummy content")  # Arquivo > 1024 bytes
            
            processor = ParquetProcessor(raw_path, silver_path)
            processor.transformer = Mock()  # Não deve ser chamado
            
            # Executar
            processor.run_all()
            
            # Verificar que não processou arquivo existente
            processor.transformer.process_zip.assert_not_called()


# Testes de integração simplificados
class TestIntegration:
    """Testes de integração entre componentes."""
    
    def test_full_pipeline_mock(self):
        """Teste pipeline completo com mocks."""
        # Mock das dependências
        mock_extractor = Mock()
        mock_transformer = Mock()
        mock_loader = Mock()
        
        # Configurar retornos
        mock_extractor.extract.return_value = [Path('file1.zip'), Path('file2.zip')]
        mock_transformer.transform.return_value = None
        mock_loader.load.return_value = None
        
        # Criar pipeline
        from src.config.pipeline_factory import ELTPipeline
        pipeline = ELTPipeline(mock_extractor, mock_transformer, mock_loader)
        
        # Executar (síncrono para teste)
        import asyncio
        asyncio.run(pipeline.run())
        
        # Verificar chamadas
        mock_extractor.extract.assert_called_once()
        mock_transformer.transform.assert_called_once()
        mock_loader.load.assert_called_once()


# Configuração do pytest
@pytest.fixture
def sample_dataframe():
    """Fixture com DataFrame de exemplo."""
    return pd.DataFrame({
        'col1': ['nan', 'valor', 'None'],
        'col2': [1, 2, 3],
        'col3': ['texto', 'NaN', 'outro']
    })


@pytest.fixture
def temp_directory():
    """Fixture com diretório temporário."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
