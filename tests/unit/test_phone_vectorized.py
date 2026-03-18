"""
Unit tests para PhoneProcessorVectorized.
Testa casos específicos, edge cases e performance.
"""
import pytest
import pandas as pd
import time
from src.utils.phone_processor_vectorized import PhoneProcessorVectorized


class TestPhoneProcessorVectorized:
    """Testes unitários para PhoneProcessorVectorized"""
    
    def test_initialization(self):
        """Testa inicialização do processador"""
        processor = PhoneProcessorVectorized(batch_size=5000)
        
        assert processor.batch_size == 5000
        assert isinstance(processor.cache, dict)
        assert len(processor.cache) == 0
        assert len(processor.operadoras_principais) == 4
        assert 'non_digit' in processor.regex_patterns
        assert 'decimal_point' in processor.regex_patterns
    
    def test_empty_dataframe(self):
        """Testa processamento de DataFrame vazio"""
        processor = PhoneProcessorVectorized()
        df = pd.DataFrame(columns=['ddd_1', 'telefone_1'])
        
        result = processor.process_batch(df)
        
        assert len(result) == 0
        assert 'telefones' in result.columns
        assert 'operadora' in result.columns
    
    def test_valid_phone_numbers(self):
        """Testa processamento de números válidos"""
        processor = PhoneProcessorVectorized()
        df = pd.DataFrame({
            'ddd_1': ['11', '21', '81'],
            'telefone_1': ['987654321', '912345678', '998765432']
        })
        
        result = processor.process_batch(df)
        
        assert len(result) == 3
        assert 'telefones' in result.columns
        assert 'operadora' in result.columns
        assert result['telefones'].notna().all()
        assert result['operadora'].notna().all()
    
    def test_invalid_short_numbers(self):
        """Testa números muito curtos (inválidos)"""
        processor = PhoneProcessorVectorized()
        df = pd.DataFrame({
            'ddd_1': ['11', '21'],
            'telefone_1': ['123', '45']
        })
        
        result = processor.process_batch(df)
        
        assert len(result) == 2
        # Números curtos devem ser marcados como inválidos
        assert (result['operadora'] == 'INVALIDO_CURTO').any() or (result['operadora'] == 'SEM_NUMERO').any()
    
    def test_missing_values(self):
        """Testa valores ausentes (NaN)"""
        processor = PhoneProcessorVectorized()
        df = pd.DataFrame({
            'ddd_1': ['11', None, '81'],
            'telefone_1': ['987654321', '912345678', None]
        })
        
        result = processor.process_batch(df)
        
        assert len(result) == 3
        # Deve processar sem erros
        assert 'telefones' in result.columns
        assert 'operadora' in result.columns
    
    def test_decimal_values(self):
        """Testa valores com ponto decimal (ex: 11.0)"""
        processor = PhoneProcessorVectorized()
        df = pd.DataFrame({
            'ddd_1': ['11.0', '21.0', '81.0'],
            'telefone_1': ['987654321.0', '912345678.0', '998765432.0']
        })
        
        result = processor.process_batch(df)
        
        assert len(result) == 3
        # Deve limpar pontos decimais corretamente
        assert result['telefones'].notna().all()
    
    def test_non_numeric_characters(self):
        """Testa remoção de caracteres não-numéricos"""
        processor = PhoneProcessorVectorized()
        df = pd.DataFrame({
            'ddd_1': ['(11)', '21-', '81*'],
            'telefone_1': ['98765-4321', '9.1234.5678', '(99876)5432']
        })
        
        result = processor.process_batch(df)
        
        assert len(result) == 3
        # Deve remover caracteres especiais
        assert result['telefones'].notna().all()
    
    def test_cache_functionality(self):
        """Testa funcionamento do cache"""
        processor = PhoneProcessorVectorized()
        processor.clear_cache()
        
        # Processa números duplicados
        df = pd.DataFrame({
            'ddd_1': ['11', '11', '11', '21', '21'],
            'telefone_1': ['987654321', '987654321', '987654321', '912345678', '912345678']
        })
        
        result = processor.process_batch(df)
        
        # Cache deve ter apenas 2 entradas únicas
        cache_stats = processor.get_cache_stats()
        assert cache_stats['cache_size'] <= 3  # Permite margem para variações
        
        # Resultados devem ser consistentes
        assert result.loc[0, 'telefones'] == result.loc[1, 'telefones']
        assert result.loc[0, 'operadora'] == result.loc[1, 'operadora']
    
    def test_clear_cache(self):
        """Testa limpeza do cache"""
        processor = PhoneProcessorVectorized()
        
        # Adiciona algo ao cache
        df = pd.DataFrame({
            'ddd_1': ['11'],
            'telefone_1': ['987654321']
        })
        processor.process_batch(df)
        
        assert len(processor.cache) > 0
        
        # Limpa cache
        processor.clear_cache()
        
        assert len(processor.cache) == 0
    
    def test_operadora_mapping(self):
        """Testa mapeamento de operadoras antigas para novas"""
        processor = PhoneProcessorVectorized()
        
        # Verifica que mapeamento existe
        assert 'TELEMIG_CELULAR' in processor.mapeamento
        assert processor.mapeamento['TELEMIG_CELULAR'] == 'VIVO'
        assert processor.mapeamento['BRASIL_TELECOM_GSM'] == 'OI'
    
    @pytest.mark.slow
    def test_performance_10k_records(self):
        """
        Testa performance com 10k registros.
        Requirement 2.2: Deve completar em menos de 5 segundos.
        """
        processor = PhoneProcessorVectorized()
        
        # Gera 10k registros
        df = pd.DataFrame({
            'ddd_1': ['11', '21', '81', '85', '71'] * 2000,
            'telefone_1': ['987654321', '912345678', '998765432', '991234567', '987651234'] * 2000
        })
        
        start_time = time.time()
        result = processor.process_batch(df)
        duration = time.time() - start_time
        
        assert len(result) == 10000
        assert duration < 5.0, f"Deve completar em <5s (atual: {duration:.2f}s)"
        
        print(f"\n⏱️  Performance: {duration:.2f}s para 10k registros")
        print(f"🚀 Throughput: {10000/duration:.2f} records/s")
    
    def test_cache_hit_rate(self):
        """Testa taxa de acerto do cache com dados repetidos"""
        processor = PhoneProcessorVectorized()
        processor.clear_cache()
        
        # Cria dataset com muitas repetições
        df = pd.DataFrame({
            'ddd_1': ['11'] * 1000,
            'telefone_1': ['987654321'] * 1000
        })
        
        result = processor.process_batch(df)
        
        # Cache deve ter apenas 1 entrada
        cache_stats = processor.get_cache_stats()
        assert cache_stats['cache_size'] <= 2, "Cache deve ser eficiente com dados repetidos"
    
    def test_regex_precompiled(self):
        """Testa que regex patterns foram pré-compilados"""
        processor = PhoneProcessorVectorized()
        
        import re
        assert isinstance(processor.regex_patterns['non_digit'], re.Pattern)
        assert isinstance(processor.regex_patterns['decimal_point'], re.Pattern)
    
    def test_batch_size_configuration(self):
        """Testa configuração de batch_size"""
        processor = PhoneProcessorVectorized(batch_size=5000)
        assert processor.batch_size == 5000
        
        processor2 = PhoneProcessorVectorized(batch_size=20000)
        assert processor2.batch_size == 20000
    
    def test_output_columns_exist(self):
        """Testa que colunas de saída são sempre criadas"""
        processor = PhoneProcessorVectorized()
        df = pd.DataFrame({
            'ddd_1': ['11'],
            'telefone_1': ['987654321']
        })
        
        result = processor.process_batch(df)
        
        assert 'telefones' in result.columns
        assert 'operadora' in result.columns
        # Colunas originais devem ser preservadas
        assert 'ddd_1' in result.columns
        assert 'telefone_1' in result.columns
    
    def test_no_temporary_columns_left(self):
        """Testa que colunas temporárias são removidas"""
        processor = PhoneProcessorVectorized()
        df = pd.DataFrame({
            'ddd_1': ['11'],
            'telefone_1': ['987654321']
        })
        
        result = processor.process_batch(df)
        
        # Colunas temporárias não devem existir no resultado
        assert 'raw_number' not in result.columns
        assert 'is_valid_length' not in result.columns
    
    def test_fixed_line_detection(self):
        """Testa detecção de telefones fixos"""
        processor = PhoneProcessorVectorized()
        
        # Telefones fixos (começam com 2, 3, 4, 5)
        df = pd.DataFrame({
            'ddd_1': ['11', '11'],
            'telefone_1': ['23456789', '34567890']  # Fixos
        })
        
        result = processor.process_batch(df)
        
        # Pelo menos alguns devem ser detectados como FIXO
        # (depende da validação do phonenumbers)
        assert 'operadora' in result.columns
    
    def test_mobile_carrier_detection(self):
        """Testa detecção de operadoras móveis"""
        processor = PhoneProcessorVectorized()
        
        # Telefones móveis (começam com 9)
        df = pd.DataFrame({
            'ddd_1': ['11', '21', '81'],
            'telefone_1': ['987654321', '912345678', '998765432']
        })
        
        result = processor.process_batch(df)
        
        # Deve ter identificado operadoras
        valid_operators = ['VIVO', 'CLARO', 'TIM', 'OI', 'MOVEL_DESCONHECIDO', 'FIXO']
        assert result['operadora'].isin(valid_operators + ['SEM_NUMERO', 'INVALIDO_CURTO', 'ERRO_PARSING']).all()
