# Benchmark Results - Pipeline ELT Otimizado

Este documento registra os resultados de benchmarks das otimizações implementadas no pipeline ELT.

## Test Environment

### Hardware
- **CPU**: [Especificar modelo e número de cores]
- **RAM**: [Especificar quantidade total]
- **Disco**: [Especificar tipo: SSD/HDD e velocidade]
- **OS**: [Especificar sistema operacional e versão]

### Software
- **Python**: [Versão]
- **PostgreSQL**: [Versão]
- **Pandas**: [Versão]
- **PyArrow**: [Versão]

### Dataset
- **Tamanho total**: [GB/registros]
- **Arquivos processados**: [Número de arquivos]
- **Período dos dados**: [Data início - Data fim]

### Configuração
```yaml
# optimization_config.yml usado nos testes
phone_processor:
  batch_size: 10000
parquet_processor:
  chunk_size: 50000
postgres_loader:
  max_workers: 4
  batch_size: 50000
```

---

## Performance Comparison

### 1. PhoneProcessor - Processamento de Telefonia

#### Baseline (Original)
| Registros | Tempo (s) | Throughput (reg/s) |
|-----------|-----------|-------------------|
| 1,000     | [tempo]   | [throughput]      |
| 10,000    | [tempo]   | [throughput]      |
| 100,000   | [tempo]   | [throughput]      |
| 1,000,000 | [tempo]   | [throughput]      |

#### Otimizado (Vetorizado)
| Registros | Tempo (s) | Throughput (reg/s) | Speedup |
|-----------|-----------|-------------------|---------|
| 1,000     | [tempo]   | [throughput]      | [X]x    |
| 10,000    | [tempo]   | [throughput]      | [X]x    |
| 100,000   | [tempo]   | [throughput]      | [X]x    |
| 1,000,000 | [tempo]   | [throughput]      | [X]x    |

**Speedup Médio**: [X]x mais rápido

**Otimizações Aplicadas**:
- ✅ Vetorização com pandas str operations
- ✅ Cache de resultados de parsing
- ✅ Regex patterns pré-compilados
- ✅ Batch processing

**Cache Performance**:
- Cache hit rate: [X]%
- Cache size: [X] entries
- Memory overhead: [X] MB

---

### 2. Conversão Parquet - Enriquecimento Integrado

#### Baseline (Enriquecimento Separado)
| Arquivo | Registros | Tempo (s) | Etapas |
|---------|-----------|-----------|--------|
| Estabelecimentos0 | [X] | [tempo] | CSV→Parquet + Enriquecimento |
| Estabelecimentos1 | [X] | [tempo] | CSV→Parquet + Enriquecimento |
| **Total** | [X] | [tempo] | 2 etapas |

#### Otimizado (Enriquecimento Integrado)
| Arquivo | Registros | Tempo (s) | Etapas | Speedup |
|---------|-----------|-----------|--------|---------|
| Estabelecimentos0 | [X] | [tempo] | CSV→Parquet enriquecido | [X]x |
| Estabelecimentos1 | [X] | [tempo] | CSV→Parquet enriquecido | [X]x |
| **Total** | [X] | [tempo] | 1 etapa | [X]x |

**Speedup Médio**: [X]x mais rápido

**Otimizações Aplicadas**:
- ✅ Enriquecimento durante conversão (elimina I/O extra)
- ✅ Processamento em chunks configuráveis
- ✅ Compressão snappy
- ✅ PhoneProcessorVectorized integrado

**I/O Reduction**:
- Leituras de disco: -50% (1 leitura vs 2)
- Escritas de disco: -50% (1 escrita vs 2)

---

### 3. Carga PostgreSQL - Processamento Paralelo

#### Baseline (Sequencial)
| Arquivos | Registros | Tempo (s) | Workers |
|----------|-----------|-----------|---------|
| 10       | [X]       | [tempo]   | 1       |
| 20       | [X]       | [tempo]   | 1       |
| 30       | [X]       | [tempo]   | 1       |

#### Otimizado (Paralelo)
| Arquivos | Registros | Tempo (s) | Workers | Speedup |
|----------|-----------|-----------|---------|---------|
| 10       | [X]       | [tempo]   | 4       | [X]x    |
| 20       | [X]       | [tempo]   | 4       | [X]x    |
| 30       | [X]       | [tempo]   | 4       | [X]x    |

**Speedup Médio**: [X]x mais rápido

**Otimizações Aplicadas**:
- ✅ ProcessPoolExecutor com múltiplos workers
- ✅ Distribuição balanceada de arquivos
- ✅ COPY command para bulk insert
- ✅ Pool de conexões otimizado

**Scaling Efficiency**:
| Workers | Speedup | Efficiency |
|---------|---------|------------|
| 1       | 1.0x    | 100%       |
| 2       | [X]x    | [X]%       |
| 4       | [X]x    | [X]%       |
| 8       | [X]x    | [X]%       |

---

### 4. Queries de Exportação - Índices Otimizados

#### Baseline (Sem Índices)
| Query | Registros Retornados | Tempo (s) | Scan Type |
|-------|---------------------|-----------|-----------|
| Nordeste por UF | [X] | [tempo] | Seq Scan |
| Nordeste por Operadora | [X] | [tempo] | Seq Scan |
| Nordeste por Ano | [X] | [tempo] | Seq Scan |

#### Otimizado (Com Índices)
| Query | Registros Retornados | Tempo (s) | Scan Type | Speedup |
|-------|---------------------|-----------|-----------|---------|
| Nordeste por UF | [X] | [tempo] | Index Scan | [X]x |
| Nordeste por Operadora | [X] | [tempo] | Index Scan | [X]x |
| Nordeste por Ano | [X] | [tempo] | Index Scan | [X]x |

**Speedup Médio**: [X]x mais rápido

**Índices Criados**:
- ✅ `idx_establ_uf_situacao_data` (composto)
- ✅ `idx_establ_operadora` (parcial)
- ✅ `idx_establ_cnpj_basico`
- ✅ `idx_establ_data_atividade` (parcial)
- ✅ `idx_establ_uf_municipio` (composto)

**Index Usage**:
| Índice | Scans | Tuples Read | Tuples Fetched |
|--------|-------|-------------|----------------|
| idx_establ_uf_situacao_data | [X] | [X] | [X] |
| idx_establ_operadora | [X] | [X] | [X] |
| idx_establ_data_atividade | [X] | [X] | [X] |

---

### 5. Pipeline End-to-End

#### Baseline (Original)
| Etapa | Tempo (s) | % do Total |
|-------|-----------|------------|
| Extract | [tempo] | [X]% |
| Transform | [tempo] | [X]% |
| Enrich | [tempo] | [X]% |
| Load | [tempo] | [X]% |
| Export | [tempo] | [X]% |
| **Total** | [tempo] | 100% |

#### Otimizado
| Etapa | Tempo (s) | % do Total | Speedup |
|-------|-----------|------------|---------|
| Extract | [tempo] | [X]% | [X]x |
| Transform + Enrich | [tempo] | [X]% | [X]x |
| Load (Paralelo) | [tempo] | [X]% | [X]x |
| Export (Índices) | [tempo] | [X]% | [X]x |
| **Total** | [tempo] | 100% | [X]x |

**Speedup Total**: [X]x mais rápido

**Time Reduction**: [X]% menos tempo

---

## Resource Usage

### CPU Utilization
| Etapa | Baseline (%) | Otimizado (%) | Cores Usados |
|-------|--------------|---------------|--------------|
| PhoneProcessor | [X] | [X] | [X] |
| Parquet Conversion | [X] | [X] | [X] |
| PostgreSQL Load | [X] | [X] | [X] |
| Export | [X] | [X] | [X] |

### Memory Usage
| Etapa | Baseline (GB) | Otimizado (GB) | Diferença |
|-------|---------------|----------------|-----------|
| PhoneProcessor | [X] | [X] | [X] GB |
| Parquet Conversion | [X] | [X] | [X] GB |
| PostgreSQL Load | [X] | [X] | [X] GB |
| Peak Usage | [X] | [X] | [X] GB |

### Disk I/O
| Métrica | Baseline | Otimizado | Redução |
|---------|----------|-----------|---------|
| Reads (GB) | [X] | [X] | [X]% |
| Writes (GB) | [X] | [X] | [X]% |
| IOPS | [X] | [X] | [X]% |

---

## Conclusion

### Summary of Improvements

**Performance Gains**:
- ✅ PhoneProcessor: [X]x mais rápido
- ✅ Parquet Conversion: [X]x mais rápido
- ✅ PostgreSQL Load: [X]x mais rápido
- ✅ Export Queries: [X]x mais rápido
- ✅ **Pipeline Total: [X]x mais rápido**

**Resource Efficiency**:
- CPU: [X]% melhor utilização
- Memory: [X]% redução de pico
- Disk I/O: [X]% redução

**Business Impact**:
- ✅ Tempo de processamento reduzido de [X]h para [X]h
- ✅ Segmentação mensal implementada
- ✅ Dashboard analítico disponível
- ✅ Queries de análise <2s

### Bottlenecks Remaining

1. **[Descrever gargalo 1]**
   - Impacto: [X]% do tempo total
   - Possível otimização: [Descrever]

2. **[Descrever gargalo 2]**
   - Impacto: [X]% do tempo total
   - Possível otimização: [Descrever]

### Recommendations

1. **Para datasets maiores (>100GB)**:
   - Aumentar `chunk_size` para 100k
   - Usar mais workers (6-8)
   - Considerar particionamento de tabelas PostgreSQL

2. **Para ambientes com menos recursos (<8GB RAM)**:
   - Reduzir `chunk_size` para 25k
   - Limitar workers para 2
   - Processar arquivos em lotes menores

3. **Para melhorar ainda mais**:
   - Implementar cache distribuído (Redis)
   - Usar Dask para processamento distribuído
   - Considerar Apache Arrow para I/O mais rápido

### Next Steps

- [ ] Executar benchmarks em ambiente de produção
- [ ] Comparar com datasets de diferentes tamanhos
- [ ] Testar em diferentes configurações de hardware
- [ ] Documentar trade-offs de configuração

---

## Appendix

### Test Commands

```bash
# Executar benchmarks
python tests/benchmarks/benchmark_baseline.py
python tests/benchmarks/benchmark_optimized.py

# Comparar resultados
python tests/benchmarks/compare_results.py

# Gerar relatório
python tests/benchmarks/generate_report.py > docs/benchmark_results.md
```

### Configuration Used

```yaml
# optimization_config.yml
phone_processor:
  batch_size: 10000
  cache_enabled: true

parquet_processor:
  chunk_size: 50000
  compression: snappy

postgres_loader:
  max_workers: 4
  batch_size: 50000
  pool_size: 20

export:
  batch_size: 50000
  use_indexes: true
```

### Data Collected

- Timestamp: [Data e hora do teste]
- Duration: [Duração total do teste]
- Dataset: [Descrição do dataset usado]
- Iterations: [Número de iterações para média]

---

**Nota**: Este é um template. Preencha os valores [X] com os resultados reais dos seus benchmarks.
