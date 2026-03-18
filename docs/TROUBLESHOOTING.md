# Guia de Troubleshooting - Pipeline ELT Otimizado

Este guia documenta problemas comuns e suas soluções para o pipeline ELT otimizado.

## Índice

1. [PhoneProcessor mais lento que esperado](#1-phoneprocessor-mais-lento-que-esperado)
2. [Paralelização não funcionando](#2-paralelização-não-funcionando)
3. [Queries de exportação lentas](#3-queries-de-exportação-lentas)
4. [Dashboard Grafana sem dados](#4-dashboard-grafana-sem-dados)
5. [Alto uso de memória](#5-alto-uso-de-memória)

---

## 1. PhoneProcessor mais lento que esperado

### Sintomas
- Processamento de telefonia levando >5s para 10k registros
- Performance similar ao PhoneProcessor original (não vetorizado)
- Cache hit rate baixo (<30%)

### Causas Possíveis

#### A. Batch size muito pequeno
**Diagnóstico:**
```python
# Verificar batch_size configurado
from src.utils.phone_processor_vectorized import PhoneProcessorVectorized
processor = PhoneProcessorVectorized()
print(f"Batch size: {processor.batch_size}")
```

**Solução:**
```yaml
# optimization_config.yml
phone_processor:
  batch_size: 10000  # Aumentar para 10k-50k
```

#### B. Dados com muitos valores únicos (baixo cache hit)
**Diagnóstico:**
```python
# Verificar diversidade de telefones
import pandas as pd
df = pd.read_parquet('data/silver_parquet/Estabelecimentos0.parquet')
unique_phones = df['telefone_1'].nunique()
total_phones = len(df)
print(f"Unique ratio: {unique_phones/total_phones:.2%}")
```

**Solução:**
- Se unique ratio >80%: Cache não ajudará muito, performance esperada
- Se unique ratio <50%: Verificar se cache está habilitado

#### C. Regex patterns não pré-compilados
**Diagnóstico:**
```python
# Verificar se patterns foram compilados
processor = PhoneProcessorVectorized()
print(f"Patterns compilados: {len(processor.regex_patterns)}")
# Deve retornar 2
```

**Solução:**
- Reinstanciar PhoneProcessorVectorized
- Verificar se __init__ está sendo chamado corretamente

### Benchmark Esperado
- 10k registros: <5s
- 100k registros: <30s
- 1M registros: <5min

---

## 2. Paralelização não funcionando

### Sintomas
- Carga PostgreSQL usando apenas 1 CPU core
- Tempo de carga similar ao modo sequencial
- Logs mostram "Usando 1 workers"

### Causas Possíveis

#### A. max_workers configurado como 1
**Diagnóstico:**
```python
from src.load.postgres_loader_parallel import PostgresLoaderParallel
loader = PostgresLoaderParallel()
print(f"Max workers: {loader.max_workers}")
```

**Solução:**
```yaml
# optimization_config.yml
postgres_loader:
  max_workers: null  # Auto-detecta CPU cores - 1
  # ou
  max_workers: 4  # Especificar manualmente
```

#### B. Poucos arquivos para paralelizar
**Diagnóstico:**
```bash
# Contar arquivos Parquet
ls data/silver_parquet/*.parquet | wc -l
```

**Solução:**
- Se <4 arquivos: Paralelização não trará ganho significativo
- Considerar processar mais arquivos simultaneamente

#### C. Limite de conexões PostgreSQL
**Diagnóstico:**
```sql
-- Verificar max_connections
SHOW max_connections;

-- Verificar conexões ativas
SELECT count(*) FROM pg_stat_activity;
```

**Solução:**
```sql
-- Aumentar max_connections (requer restart)
ALTER SYSTEM SET max_connections = 100;
```

```yaml
# optimization_config.yml
postgres_loader:
  max_workers: 4  # Reduzir se atingir limite de conexões
```

### Benchmark Esperado
- 4 workers: ~2.5x mais rápido que sequencial
- 8 workers: ~3.5x mais rápido (diminishing returns)

---

## 3. Queries de exportação lentas

### Sintomas
- Exportação Nordeste levando >2s por query
- EXPLAIN ANALYZE mostra Seq Scan
- Índices não sendo utilizados

### Causas Possíveis

#### A. Índices não criados
**Diagnóstico:**
```sql
-- Verificar índices existentes
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE tablename = 'estabelecimentos';
```

**Solução:**
```bash
# Criar índices otimizados
psql -U postgres -d receita_federal -f src/database/create_indexes.sql
```

#### B. Estatísticas desatualizadas
**Diagnóstico:**
```sql
-- Verificar última análise
SELECT schemaname, tablename, last_analyze, last_autoanalyze
FROM pg_stat_user_tables
WHERE tablename = 'estabelecimentos';
```

**Solução:**
```sql
-- Atualizar estatísticas
ANALYZE estabelecimentos;
ANALYZE empresas;
```

#### C. Query não usando índices corretos
**Diagnóstico:**
```sql
-- Verificar plano de execução
EXPLAIN ANALYZE
SELECT * FROM estabelecimentos
WHERE uf = 'BA' 
  AND situacao_cadastral = '02'
  AND data_inicio_atividade >= '2020-01-01';
```

**Solução:**
- Verificar se índice composto existe: `idx_establ_uf_situacao_data`
- Verificar ordem das colunas no WHERE (deve corresponder ao índice)
- Considerar criar índice parcial se filtro é sempre o mesmo

### Benchmark Esperado
- Query com índices: <2s
- Query sem índices: >30s

---

## 4. Dashboard Grafana sem dados

### Sintomas
- Painéis do Grafana vazios ou "No data"
- Métricas não aparecem no Prometheus
- Dashboard não carrega

### Causas Possíveis

#### A. Prometheus não coletando métricas
**Diagnóstico:**
```bash
# Verificar endpoint de métricas
curl http://localhost:8000/metrics

# Verificar targets do Prometheus
curl http://localhost:9091/api/v1/targets
```

**Solução:**
```yaml
# prom_config.yml - Verificar configuração
scrape_configs:
  - job_name: 'python_elt'
    scrape_interval: 5s
    static_configs:
      - targets: ['elt_pipeline:8000']
```

```bash
# Reiniciar Prometheus
docker-compose restart prometheus
```

#### B. Data source não configurado
**Diagnóstico:**
- Acessar Grafana: http://localhost:3001
- Configuration → Data Sources
- Verificar se Prometheus está configurado

**Solução:**
1. Add data source → Prometheus
2. URL: `http://prometheus:9090`
3. Access: Server (default)
4. Save & Test

#### C. Pipeline não executou ainda
**Diagnóstico:**
```bash
# Verificar se métricas existem
curl http://localhost:9091/api/v1/query?query=elt_files_processed_total
```

**Solução:**
- Executar pipeline pelo menos uma vez
- Métricas só aparecem após primeira execução

#### D. Dashboard JSON inválido
**Diagnóstico:**
```bash
# Validar JSON
python -c "import json; json.load(open('grafana_dashboard.json'))"
```

**Solução:**
- Corrigir erros de sintaxe JSON
- Reimportar dashboard no Grafana

### Verificação de Saúde
```bash
# Executar testes de verificação
python -m pytest tests/verification/test_grafana_setup.py -v
python -m pytest tests/verification/test_prometheus_metrics.py -v
```

---

## 5. Alto uso de memória

### Sintomas
- Processo Python usando >8GB RAM
- Sistema ficando lento durante pipeline
- OOM (Out of Memory) errors

### Causas Possíveis

#### A. chunk_size muito grande
**Diagnóstico:**
```python
# Verificar chunk_size configurado
from src.transform.optimized_parquet_processor import OptimizedParquetProcessor
processor = OptimizedParquetProcessor(...)
print(f"Chunk size: {processor.chunk_size}")
```

**Solução:**
```yaml
# optimization_config.yml
parquet_processor:
  chunk_size: 25000  # Reduzir de 50k para 25k
```

#### B. Muitos workers paralelos
**Diagnóstico:**
```bash
# Verificar uso de memória por processo
ps aux | grep python | awk '{print $6/1024 " MB - " $11}'
```

**Solução:**
```yaml
# optimization_config.yml
postgres_loader:
  max_workers: 2  # Reduzir número de workers
```

#### C. Cache de telefonia muito grande
**Diagnóstico:**
```python
# Verificar tamanho do cache
from src.utils.phone_processor_vectorized import PhoneProcessorVectorized
processor = PhoneProcessorVectorized()
# Após processar alguns batches
print(f"Cache size: {len(processor.cache)} entries")
```

**Solução:**
```python
# Limpar cache periodicamente
processor.cache.clear()
```

#### D. DataFrames não sendo liberados
**Diagnóstico:**
```python
import gc
import psutil
import os

process = psutil.Process(os.getpid())
print(f"Memory: {process.memory_info().rss / 1024 / 1024:.2f} MB")
print(f"Objects: {len(gc.get_objects())}")
```

**Solução:**
```python
# Forçar garbage collection
import gc
gc.collect()

# Deletar DataFrames explicitamente
del df
gc.collect()
```

### Uso de Memória Esperado
- Baseline: ~500MB
- Durante processamento: ~2-4GB
- Pico (paralelização): ~6-8GB

### Configuração Recomendada por Ambiente

#### Ambiente de Desenvolvimento (8GB RAM)
```yaml
phone_processor:
  batch_size: 5000
parquet_processor:
  chunk_size: 25000
postgres_loader:
  max_workers: 2
```

#### Ambiente de Produção (16GB+ RAM)
```yaml
phone_processor:
  batch_size: 10000
parquet_processor:
  chunk_size: 50000
postgres_loader:
  max_workers: 4
```

---

## Ferramentas de Diagnóstico

### Script de Diagnóstico Completo
```bash
# Executar diagnóstico completo
python tests/verification/test_system_health.py
```

### Monitoramento em Tempo Real
```bash
# CPU e Memória
watch -n 1 'ps aux | grep python'

# Conexões PostgreSQL
watch -n 1 'psql -U postgres -d receita_federal -c "SELECT count(*) FROM pg_stat_activity"'

# Métricas Prometheus
curl http://localhost:9091/api/v1/query?query=elt_processing_duration_seconds
```

### Logs Detalhados
```python
# Habilitar debug logging
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## Suporte

Se o problema persistir após seguir este guia:

1. Verificar logs detalhados em `logs/pipeline.log`
2. Executar suite de testes: `pytest tests/ -v`
3. Verificar configuração em `optimization_config.yml`
4. Consultar documentação em `docs/OPTIMIZATION_GUIDE.md`

## Referências

- [OPTIMIZATION_GUIDE.md](./OPTIMIZATION_GUIDE.md) - Guia de otimização
- [README_OPTIMIZATIONS.md](../README_OPTIMIZATIONS.md) - Visão geral das otimizações
- [Design Document](.kiro/specs/pipeline-optimization-and-analytics-dashboard/design.md)
