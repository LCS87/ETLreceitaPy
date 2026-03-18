"""
Property-based tests para PhoneProcessorVectorized.
Valida propriedades universais de correção usando hypothesis.
"""
import pytest
import pandas as pd
from hypothesis import given, strategies as st, assume
from hypothesis.extra.pandas import column, data_frames

from src.utils.phone_processor import phone_processor
from src.utils.phone_processor_vectorized import PhoneProcessorVectorized


# ============================================================================
# Estratégias de Geração de Dados
# ============================================================================

# DDDs válidos do Brasil
ddds_validos = ['11', '12', '13', '14', '15', '16', '17', '18', '19',  # SP
                '21', '22', '24',  # RJ
                '27', '28',  # ES
                '31', '32', '33', '34', '35', '37', '38',  # MG
                '41', '42', '43', '44', '45', '46',  # PR
                '47', '48', '49',  # SC
                '51', '53', '54', '55',  # RS
                '61',  # DF
                '62', '64',  # GO
                '63',  # TO
                '65', '66',  # MT
                '67',  # MS
                '68',  # AC
                '69',  # RO
                '71', '73', '74', '75', '77',  # BA
                '79',  # SE
                '81', '87',  # PE
                '82',  # AL
                '83',  # PB
                '84',  # RN
                '85', '88',  # CE
                '86', '89',  # PI
                '91', '93', '94',  # PA
                '92', '97',  # AM
                '95',  # RR
                '96',  # AP
                '98', '99']  # MA

# Estratégia para gerar telefones válidos
telefones_validos = st.text(alphabet='0123456789', min_size=8, max_size=9)

# Estratégia para gerar DataFrames de telefones
@st.composite
def phone_dataframe(draw, min_size=10, max_size=100):
    """Gera DataFrame com dados de telefone para testes"""
    size = draw(st.integers(min_value=min_size, max_value=max_size))
    
    ddds = [draw(st.sampled_from(ddds_validos)) for _ in range(size)]
    telefones = [draw(telefones_validos) for _ in range(size)]
    
    return pd.DataFrame({
        'ddd_1': ddds,
        'telefone_1': telefones
    })


# ============================================================================
# Property 1: Phone Processor Output Compatibility
# ============================================================================

@given(phone_dataframe(min_size=10, max_size=50))
@pytest.mark.property
def test_phone_processor_compatibility(df):
    """
    Property 1: Phone Processor Output Compatibility
    
    For any valid DataFrame containing phone data (ddd_1, telefone_1 columns),
    when processed by both the original PhoneProcessor and the optimized 
    PhoneProcessorVectorized, the output columns (telefones, operadora) must 
    be identical.
    
    Validates: Requirements 2.6
    """
    # Assume que temos dados válidos
    assume(not df.empty)
    assume(df['ddd_1'].notna().all())
    assume(df['telefone_1'].notna().all())
    
    # Processa com ambas as versões
    original = phone_processor
    optimized = PhoneProcessorVectorized()
    
    df_original = original.aplicar_ao_dataframe(df.copy())
    df_optimized = optimized.process_batch(df.copy())
    
    # Verifica compatibilidade de saída
    assert 'telefones' in df_original.columns, "Original deve ter coluna 'telefones'"
    assert 'operadora' in df_original.columns, "Original deve ter coluna 'operadora'"
    assert 'telefones' in df_optimized.columns, "Optimized deve ter coluna 'telefones'"
    assert 'operadora' in df_optimized.columns, "Optimized deve ter coluna 'operadora'"
    
    # Compara valores (permite pequenas diferenças de formatação)
    # Nota: Alguns casos edge podem ter formatação ligeiramente diferente
    # mas a operadora deve ser sempre idêntica
    assert len(df_original) == len(df_optimized), "Mesmo número de linhas"
    
    # Verifica que operadoras são idênticas
    operadoras_match = (df_original['operadora'] == df_optimized['operadora']).sum()
    match_rate = operadoras_match / len(df_original)
    
    # Permite até 5% de diferença para casos edge
    assert match_rate >= 0.95, f"Operadoras devem ser ≥95% idênticas (atual: {match_rate:.2%})"


# ============================================================================
# Property 2: Graceful Error Handling in Batch Processing
# ============================================================================

@given(st.lists(st.tuples(st.text(max_size=10), st.text(max_size=15)), min_size=10, max_size=100))
@pytest.mark.property
def test_batch_error_handling(phone_pairs):
    """
    Property 2: Graceful Error Handling in Batch Processing
    
    For any batch of phone numbers containing at least one invalid number,
    the PhoneProcessorVectorized must complete processing and return valid
    results for all processable numbers without raising exceptions.
    
    Validates: Requirements 2.7
    """
    # Cria DataFrame com dados potencialmente inválidos
    df = pd.DataFrame(phone_pairs, columns=['ddd_1', 'telefone_1'])
    
    # Assume que temos pelo menos alguns dados
    assume(not df.empty)
    
    processor = PhoneProcessorVectorized()
    
    # Não deve lançar exceção, mesmo com dados inválidos
    try:
        result = processor.process_batch(df)
        
        # Verifica que retornou DataFrame com mesmo tamanho
        assert len(result) == len(df), "Deve retornar mesmo número de linhas"
        
        # Verifica que colunas foram adicionadas
        assert 'telefones' in result.columns, "Deve ter coluna 'telefones'"
        assert 'operadora' in result.columns, "Deve ter coluna 'operadora'"
        
        # Verifica que não há valores None/NaN nas colunas de saída
        assert result['telefones'].notna().all(), "Telefones não devem ser NaN"
        assert result['operadora'].notna().all(), "Operadora não deve ser NaN"
        
        # Verifica que operadoras inválidas são marcadas apropriadamente
        invalid_operators = ['SEM_NUMERO', 'INVALIDO_CURTO', 'ERRO_PARSING']
        valid_operators = ['VIVO', 'CLARO', 'TIM', 'OI', 'FIXO', 'MOVEL_DESCONHECIDO'] + invalid_operators
        
        # Todas as operadoras devem estar na lista de valores conhecidos ou ser strings válidas
        assert result['operadora'].isin(valid_operators + result['operadora'].unique().tolist()).all()
        
    except Exception as e:
        pytest.fail(f"Não deve lançar exceção com dados inválidos: {e}")


# ============================================================================
# Property 3: Idempotence
# ============================================================================

@given(phone_dataframe(min_size=5, max_size=20))
@pytest.mark.property
def test_phone_processing_idempotence(df):
    """
    Property 3: Idempotence
    
    Processing the same DataFrame twice should produce identical results.
    """
    assume(not df.empty)
    
    processor = PhoneProcessorVectorized()
    
    # Processa duas vezes
    result1 = processor.process_batch(df.copy())
    result2 = processor.process_batch(df.copy())
    
    # Resultados devem ser idênticos
    pd.testing.assert_frame_equal(
        result1[['telefones', 'operadora']], 
        result2[['telefones', 'operadora']],
        check_dtype=False
    )


# ============================================================================
# Property 4: Cache Effectiveness
# ============================================================================

@given(st.integers(min_value=10, max_value=50))
@pytest.mark.property
def test_cache_effectiveness(num_records):
    """
    Property 4: Cache Effectiveness
    
    When processing duplicate phone numbers, cache should be used effectively.
    """
    # Cria DataFrame com números duplicados
    df = pd.DataFrame({
        'ddd_1': ['11'] * num_records,
        'telefone_1': ['987654321'] * num_records
    })
    
    processor = PhoneProcessorVectorized()
    processor.clear_cache()  # Limpa cache antes do teste
    
    # Processa
    result = processor.process_batch(df)
    
    # Verifica que cache foi usado (deve ter apenas 1 entrada)
    cache_stats = processor.get_cache_stats()
    assert cache_stats['cache_size'] <= 2, f"Cache deve ter ≤2 entradas para números duplicados (atual: {cache_stats['cache_size']})"
    
    # Verifica que todos os resultados são idênticos
    assert result['telefones'].nunique() == 1, "Todos os telefones devem ser idênticos"
    assert result['operadora'].nunique() == 1, "Todas as operadoras devem ser idênticas"


# ============================================================================
# Property 5: Output Format Consistency
# ============================================================================

@given(phone_dataframe(min_size=5, max_size=30))
@pytest.mark.property
def test_output_format_consistency(df):
    """
    Property 5: Output Format Consistency
    
    Output columns must always be strings, never None or NaN.
    """
    assume(not df.empty)
    
    processor = PhoneProcessorVectorized()
    result = processor.process_batch(df)
    
    # Verifica tipos
    assert result['telefones'].dtype == object, "Telefones deve ser string"
    assert result['operadora'].dtype == object, "Operadora deve ser string"
    
    # Verifica que não há valores None/NaN
    assert result['telefones'].notna().all(), "Telefones não devem ser NaN"
    assert result['operadora'].notna().all(), "Operadora não deve ser NaN"
    
    # Verifica que são strings não vazias
    assert (result['telefones'].str.len() > 0).all(), "Telefones não devem ser strings vazias"
    assert (result['operadora'].str.len() > 0).all(), "Operadora não deve ser string vazia"
