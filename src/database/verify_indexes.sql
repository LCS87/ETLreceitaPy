-- ============================================================================
-- Script de Verificação de Índices
-- Pipeline ELT - Receita Federal
-- ============================================================================
-- Verifica existência, tamanho e uso dos índices criados
-- ============================================================================
-- 1. Listar todos os índices da tabela estabelecimentos
SELECT indexname,
    indexdef
FROM pg_indexes
WHERE tablename = 'estabelecimentos'
ORDER BY indexname;
-- 2. Verificar tamanho dos índices
SELECT schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size,
    pg_size_pretty(pg_table_size(tablename::regclass)) as table_size
FROM pg_stat_user_indexes
WHERE tablename = 'estabelecimentos'
ORDER BY pg_relation_size(indexrelid) DESC;
-- 3. Verificar uso dos índices (requer pg_stat_statements ou histórico)
SELECT schemaname,
    tablename,
    indexname,
    idx_scan as index_scans,
    idx_tup_read as tuples_read,
    idx_tup_fetch as tuples_fetched,
    CASE
        WHEN idx_scan = 0 THEN 'NUNCA USADO'
        WHEN idx_scan < 100 THEN 'POUCO USADO'
        ELSE 'BEM USADO'
    END as usage_status
FROM pg_stat_user_indexes
WHERE tablename = 'estabelecimentos'
ORDER BY idx_scan DESC;
-- 4. Verificar índices não utilizados (candidatos para remoção)
SELECT schemaname,
    tablename,
    indexname,
    idx_scan,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size
FROM pg_stat_user_indexes
WHERE tablename = 'estabelecimentos'
    AND idx_scan = 0
    AND indexrelid IS NOT NULL
ORDER BY pg_relation_size(indexrelid) DESC;
-- 5. Verificar índices parciais (com WHERE clause)
SELECT schemaname,
    tablename,
    indexname,
    pg_get_indexdef(indexrelid) as index_definition
FROM pg_stat_user_indexes
WHERE tablename = 'estabelecimentos'
    AND pg_get_indexdef(indexrelid) LIKE '%WHERE%'
ORDER BY indexname;
-- 6. Estatísticas de uso de índices compostos
SELECT indexname,
    idx_scan,
    idx_tup_read,
    idx_tup_fetch,
    ROUND(
        100.0 * idx_tup_fetch / NULLIF(idx_tup_read, 0),
        2
    ) as fetch_ratio
FROM pg_stat_user_indexes
WHERE tablename = 'estabelecimentos'
    AND idx_scan > 0
ORDER BY idx_scan DESC;
-- 7. Verificar bloat (inchaço) dos índices
SELECT schemaname,
    tablename,
    indexname,
    pg_size_pretty(pg_relation_size(indexrelid)) as index_size,
    CASE
        WHEN pg_relation_size(indexrelid) > 1073741824 THEN 'GRANDE (>1GB)'
        WHEN pg_relation_size(indexrelid) > 104857600 THEN 'MÉDIO (>100MB)'
        ELSE 'PEQUENO'
    END as size_category
FROM pg_stat_user_indexes
WHERE tablename = 'estabelecimentos'
ORDER BY pg_relation_size(indexrelid) DESC;