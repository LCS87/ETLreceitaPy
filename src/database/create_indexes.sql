-- ============================================================================
-- Script de Criação de Índices Otimizados
-- Pipeline ELT - Receita Federal
-- ============================================================================
-- Executar após carga inicial de dados
-- Usa CREATE INDEX CONCURRENTLY para não bloquear tabela
-- ============================================================================
-- Índice composto principal para queries de exportação
-- Cobre os 3 filtros principais: UF, situacao_cadastral, data_inicio_atividade
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_establ_uf_situacao_data ON estabelecimentos (uf, situacao_cadastral, data_inicio_atividade)
WHERE situacao_cadastral = '02';
-- Índice parcial para filtro de operadora
-- Reduz tamanho do índice incluindo apenas operadoras principais
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_establ_operadora ON estabelecimentos (operadora)
WHERE operadora IN ('VIVO', 'CLARO', 'TIM', 'OI');
-- Índice para join com tabela empresas
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_establ_cnpj_basico ON estabelecimentos (cnpj_basico);
-- Índice parcial para análise temporal
-- Inclui apenas dados recentes (a partir de 2020)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_establ_data_atividade ON estabelecimentos (data_inicio_atividade)
WHERE data_inicio_atividade >= '2020-01-01';
-- Índice para análise geográfica (agregações por município)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_establ_uf_municipio ON estabelecimentos (uf, municipio);
-- Índice composto parcial: ativos por UF (filtro mais frequente da interface web)
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_establ_uf_ativo ON estabelecimentos (uf, municipio)
WHERE situacao_cadastral = '02';
-- Extensão + índices de trigramas para ILIKE '%texto%' em bairro/cidade
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_establ_bairro_trgm ON estabelecimentos USING GIN (bairro gin_trgm_ops);
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_municipios_descricao_trgm ON municipios USING GIN (descricao gin_trgm_ops);
-- Índice na tabela empresas para join
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_emp_cnpj_basico ON empresas (cnpj_basico);
-- Índice na tabela socios para join
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_soc_cnpj_basico ON socios (cnpj_basico);
-- Atualizar estatísticas para otimizador de queries
ANALYZE estabelecimentos;
ANALYZE empresas;
ANALYZE socios;
-- ============================================================================
-- Verificação de Criação
-- ============================================================================
SELECT schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE tablename IN ('estabelecimentos', 'empresas', 'socios')
ORDER BY tablename,
    indexname;