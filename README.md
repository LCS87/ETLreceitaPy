# Pipeline ELT: Dados Abertos CNPJ — Receita Federal

Pipeline de engenharia de dados para extração, transformação e carga dos dados públicos de CNPJ da Receita Federal, com exportação de leads segmentados por operadora de telefonia, porte empresarial e período (anual, trimestral e mensal).

---

## Índice

- [Visão Geral](#visão-geral)
- [Stack de Tecnologias](#stack-de-tecnologias)
- [Arquitetura do Pipeline](#arquitetura-do-pipeline)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Pré-requisitos](#pré-requisitos)
- [Configuração do Ambiente](#configuração-do-ambiente)
- [Executando com Docker](#executando-com-docker)
- [Executando sem Docker (Local)](#executando-sem-docker-local)
- [Exportação de Leads](#exportação-de-leads)
- [Monitoramento](#monitoramento)
- [Variáveis de Ambiente](#variáveis-de-ambiente)
- [Troubleshooting](#troubleshooting)

---

## Visão Geral

O pipeline processa os arquivos públicos disponibilizados pela Receita Federal (portal de dados abertos) e gera listas de leads de empresas do Nordeste brasileiro, segmentadas por:

- **Tipo de empresa:** MEI, ME, LTDA
- **Operadora de telefonia:** CLARO, TIM, VIVO, OI, FIXO, etc.
- **Período:** anual, trimestral e mensal
- **Estado:** AL, BA, CE, MA, PB, PE, PI, RN, SE

Volume processado: ~70 milhões de estabelecimentos, ~45 milhões de empresas, ~47 milhões de registros Simples Nacional.

---

## 📊 Dashboard Analytics em Destaque

O projeto agora conta com um dashboard interativo (com **Modo Escuro** e **Filtros por Região**), para visualização assertiva da inteligência comercial de Banda Larga e Telefonia extraída.

### KPIs e Evolução Mensal
![Visão Geral KPIs e Gráficos](assets/tela01.png)

### Distribuição Geográfica e Tipos de Empresa
![Mapa de Calor e Distribuição](assets/tela02.png)

### Análise de Mercado por Estado (%)
![Detalhes por Estado Heatmap](assets/tela03.png)

### Potencial Comercial de Vendas (Banda Larga e Telefonia)
![Potencial de Vendas e Crescimento B2B](assets/tela04.png)

### Dados Detalhados por Estado
![Tabela de Dados Consolidados](assets/tela05.png)

---

## Stack de Tecnologias

### Linguagem e Runtime
| Tecnologia | Versão | Uso |
|---|---|---|
| Python | 3.10+ | Runtime principal |
| asyncio / aiohttp | 3.8+ | Downloads paralelos assíncronos |

### Processamento de Dados
| Tecnologia | Versão | Uso |
|---|---|---|
| Pandas | 2.0+ | Manipulação de DataFrames em chunks |
| PyArrow | 12.0+ | Leitura/escrita Parquet colunar |
| NumPy | 1.24+ | Operações vetorizadas |
| phonenumbers | 8.13+ | Identificação de operadora por DDD/número |

### Banco de Dados
| Tecnologia | Versão | Uso |
|---|---|---|
| PostgreSQL | 15 | Data Warehouse principal |
| SQLAlchemy | 2.0+ | ORM e gerenciamento de conexões |
| psycopg2-binary | 2.9+ | Driver PostgreSQL (COPY bulk load) |

### Monitoramento
| Tecnologia | Versão | Uso |
|---|---|---|
| Prometheus | latest | Coleta de métricas do pipeline |
| Grafana | latest | Dashboards em tempo real |
| prometheus-client | 0.17+ | Exposição de métricas via HTTP |
| psutil | 5.9+ | Métricas de CPU, RAM e disco |
| node-exporter | latest | Métricas do sistema operacional |

### Infraestrutura
| Tecnologia | Versão | Uso |
|---|---|---|
| Docker | 20+ | Containerização dos serviços |
| Docker Compose | v2 | Orquestração local |
| python-dotenv | 1.0+ | Gerenciamento de variáveis de ambiente |

---

## Arquitetura do Pipeline

```
Portal Receita Federal
        |
        v
[1. EXTRACT]  async_download.py
  aiohttp + asyncio
  Downloads paralelos (8 conexões)
  Retry automático com backoff
        |
        v  data/raw_zips/*.zip
        |
[2. TRANSFORM]  optimized_parquet_processor.py
  Extração ZIP em memória
  Normalização de colunas
  Enriquecimento de telefonia (operadora por DDD)
  Escrita em Parquet colunar (chunks de 500k linhas)
        |
        v  data/silver_parquet/*.parquet
        |
[3. LOAD]  postgres_adapter.py
  TRUNCATE das tabelas (evita duplicatas)
  PostgreSQL COPY bulk load
  Criação de índices de performance
        |
        v  PostgreSQL (receita_db)
        |
[4. EXPORT]  nordeste_exporter_optimized.py
  Query SQL com LEFT JOIN (empresas + simples)
  Classificação MEI/ME/LTDA
  Segmentação por UF, operadora, ano/trimestre/mês
        |
        v  data/silver_parquet/exports_final/
```

### Tabelas no PostgreSQL

| Tabela | Descrição | Volume aprox. |
|---|---|---|
| `estabelecimentos` | Dados de endereço, telefone, situação | 70M registros |
| `empresas` | Razão social, porte, natureza jurídica | 45M registros |
| `simples` | Opção MEI/Simples Nacional | 47M registros |
| `socios` | Quadro societário | variável |
| `cnaes` | Tabela de atividades econômicas | ~1.3k registros |
| `municipios` | Tabela de municípios | ~5.5k registros |
| `naturezas` | Naturezas jurídicas | ~90 registros |
| `paises` | Tabela de países | ~260 registros |
| `qualificacoes` | Qualificações de sócios | ~70 registros |
| `motivos` | Motivos de situação cadastral | ~60 registros |

---

## Estrutura do Projeto

```
ETLreceitaPy/
├── app_entrypoint.py                   # Orquestrador principal do pipeline
├── run_export.py                       # Exportação standalone (sem reprocessar)
├── check_system.py                     # Diagnóstico pré-execução
├── docker-compose.yml                  # Serviços Docker
├── prom_config.yml                     # Configuração do Prometheus
├── grafana_dashboard.json              # Dashboard importável no Grafana
├── requirements.txt
├── .env                                # Variáveis de ambiente (não versionar)
│
├── src/
│   ├── config/
│   │   └── pipeline_factory.py         # Factory Pattern — injeção de dependências
│   ├── core/
│   │   └── interfaces.py               # Interfaces Protocol (SOLID)
│   ├── extract/
│   │   └── async_download.py           # Download assíncrono com retry
│   ├── transform/
│   │   └── optimized_parquet_processor.py  # ZIP -> Parquet com enriquecimento
│   ├── load/
│   │   └── postgres_adapter.py         # Bulk load via PostgreSQL COPY
│   ├── exports/
│   │   └── nordeste_exporter_optimized.py  # Exportação de leads CSV
│   ├── monitoring/
│   │   └── prometheus_stats.py         # Métricas Prometheus
│   └── utils/
│       ├── env_loader.py               # Configurações e detecção de hardware
│       ├── log_handler.py              # Logging estruturado
│       └── phone_processor.py          # Identificação de operadora
│
├── infra/
│   └── Dockerfile_app                  # Imagem Docker do pipeline
│
├── dags/
│   └── workflow_receita.py             # DAG Airflow (opcional)
│
└── data/
    ├── raw_zips/                       # Arquivos .zip baixados
    └── silver_parquet/                 # Parquet processados + exports CSV
        └── exports_final/
            ├── 1_Processo_Anual/
            ├── 2_Processo_Trimestral/
            └── 3_Processo_Mensal/
```

---

## Pré-requisitos

### Com Docker (recomendado)
- Docker 20+
- Docker Compose v2
- ~100GB de espaço em disco

### Sem Docker (local)
- Python 3.10+
- PostgreSQL 15 instalado e rodando localmente
- ~100GB de espaço em disco

### Hardware recomendado
- CPU: 6+ cores (otimizado para Ryzen 5 3600 / 12 threads)
- RAM: 32GB+ (48GB ideal para chunks de 500k linhas)
- Disco: NVMe SSD (leitura/escrita intensiva de Parquet)

---

## Configuração do Ambiente

### 1. Clonar o repositório

```bash
git clone <seu-repo>
cd ETLreceitaPy
```

### 2. Criar e ativar o virtual environment

```bash
# Criar
python -m venv venv

# Ativar — Windows PowerShell
venv\Scripts\Activate.ps1

# Ativar — Windows CMD
venv\Scripts\activate.bat

# Ativar — Linux/Mac
source venv/bin/activate
```

### 3. Instalar dependências

```bash
pip install -r requirements.txt
```

### 4. Configurar variáveis de ambiente

```bash
# Windows
copy .env.example .env

# Linux/Mac
cp .env.example .env
```

Edite o `.env` conforme necessário (ver seção [Variáveis de Ambiente](#variáveis-de-ambiente)).

---

## Executando com Docker

O Docker Compose sobe todos os serviços necessários: PostgreSQL, o pipeline ELT, Prometheus, Grafana e Node Exporter.

### Subir todos os serviços

```bash
docker-compose up -d
```

### Verificar status

```bash
docker-compose ps
```

### Acompanhar logs em tempo real

```bash
# Todos os serviços
docker-compose logs -f

# Apenas o pipeline
docker-compose logs -f elt_pipeline

# Apenas o banco
docker-compose logs -f postgres_receita
```

### Parar os serviços

```bash
# Para os containers (mantém os dados)
docker-compose down

# Para e remove os volumes (apaga o banco de dados)
docker-compose down -v
```

### Rebuild da imagem após alterações no código

```bash
docker-compose build --no-cache elt_pipeline
docker-compose up -d elt_pipeline
```

### Acessar o banco de dados via container

```bash
docker-compose exec postgres_receita psql -U admin_receita -d receita_db
```

### Serviços e portas (Docker)

| Serviço | Porta local | Descrição |
|---|---|---|
| PostgreSQL | 5433 | Banco de dados (mapeado de 5432 interno) |
| Prometheus | 9091 | Coleta de métricas (mapeado de 9090 interno) |
| Grafana | 3001 | Dashboards (mapeado de 3000 interno) |
| Node Exporter | 9100 | Métricas do SO |
| Pipeline (métricas) | 8000 | Endpoint `/metrics` do Prometheus |

> O PostgreSQL fica na porta **5433** (não 5432) para evitar conflito com instalações locais.

---

## Executando sem Docker (Local)

Para rodar sem Docker, você precisa de um PostgreSQL local instalado e configurado.

### 1. Instalar e configurar o PostgreSQL

Baixe e instale o PostgreSQL 15: https://www.postgresql.org/download/

Após instalar, crie o banco e o usuário:

```sql
-- Conecte como superusuário (psql -U postgres)
CREATE USER admin_receita WITH PASSWORD 'receita@2026';
CREATE DATABASE receita_db OWNER admin_receita;
GRANT ALL PRIVILEGES ON DATABASE receita_db TO admin_receita;
```

### 2. Ajustar o .env para conexão local

```dotenv
DB_HOST=localhost
DB_PORT=5432        # porta padrão do PostgreSQL local
DB_NAME=receita_db
DB_USER=admin_receita
DB_PASS=receita@2026
```

### 3. Verificar o sistema antes de rodar

```bash
py check_system.py
```

Saída esperada:
```
[1/4] Verificando acesso ao Disco...     OK
[2/4] Verificando PostgreSQL...          Conexão OK
[3/4] Verificando portas...              OK
[4/4] Verificando Bibliotecas...         Todas instaladas
```

### 4. Rodar o pipeline completo

```bash
py app_entrypoint.py
```

O pipeline executa automaticamente todas as etapas:
1. Download dos arquivos .zip da Receita Federal
2. Transformação CSV → Parquet com enriquecimento de telefonia
3. Carga bulk no PostgreSQL (TRUNCATE + COPY)
4. Criação de índices de performance
5. Exportação de leads Nordeste em CSV

Tempo estimado (Ryzen 5 3600 / 48GB / NVMe): 2 a 4 horas para o pipeline completo.

### 5. Rodar apenas a exportação

Se os dados já estão no banco e você quer apenas re-exportar os CSVs:

```bash
py run_export.py
```

Tempo estimado: ~3 minutos para 1,8 milhão de registros.

### Monitoramento sem Docker

O pipeline expõe métricas Prometheus na porta 8000 automaticamente. Para visualizar no Grafana sem Docker, instale o Grafana localmente e aponte para `http://localhost:8000/metrics`.

---

## Exportação de Leads

### Estrutura dos arquivos gerados

```
data/silver_parquet/exports_final/
├── 1_Processo_Anual/
│   └── {UF}/
│       └── {UF} - {TIPO} {ANO} - {OPERADORA}.csv
│           ex: BA - MEI 2024 - CLARO.csv
│
├── 2_Processo_Trimestral/
│   └── {UF}/
│       └── {UF} - T{N} {ANO} {TIPO} - {OPERADORA}.csv
│           ex: PE - T2 2024 ME - TIM.csv
│
└── 3_Processo_Mensal/
    └── {UF}/
        └── {UF} - {TIPO} {ANO}-{MM} - {OPERADORA}.csv
            ex: CE - LTDA 2024-06 - VIVO.csv
```

### Filtros aplicados

| Filtro | Valor |
|---|---|
| Estados | AL, BA, CE, MA, PB, PE, PI, RN, SE |
| Período | 2023 até ano atual |
| Situação cadastral | 02 (Ativa) |
| Telefone | Obrigatório (não nulo, não vazio) |

### Classificação de tipo de empresa

| Tipo | Critério |
|---|---|
| MEI | `simples.opcao_pelo_mei = 'S'` e `data_exclusao_mei = '00000000'` |
| ME | `empresas.porte_empresa IN ('01', '03')` (ME e EPP unificados) |
| LTDA | Demais casos |

### Colunas dos arquivos CSV

```
cnpj_completo | razao_social | endereco_completo | email | ano | telefone | operadora | tipo_empresa
```

Separador: `|` (pipe)
Encoding: UTF-8 BOM (compatível com Excel)

---

## Monitoramento

### Acessar o Grafana

URL: http://localhost:3001
Credenciais: `admin` / `admin`

Para importar o dashboard:
1. Acesse `Dashboards > Import`
2. Clique em `Upload dashboard JSON file`
3. Selecione o arquivo `grafana_dashboard.json` na raiz do projeto
4. Clique em `Import`

### Métricas disponíveis (Prometheus)

| Métrica | Descrição |
|---|---|
| `elt_files_processed_total` | Total de arquivos processados por etapa |
| `elt_rows_inserted_total` | Linhas inseridas no banco por tabela |
| `elt_stage_duration_seconds` | Duração de cada etapa do pipeline |
| `elt_export_query_duration_seconds` | Tempo das queries de exportação |
| `system_cpu_usage_percent` | Uso de CPU em tempo real |
| `system_ram_usage_percent` | Uso de RAM em tempo real |

### Acessar métricas diretamente

```bash
# Endpoint Prometheus do pipeline
curl http://localhost:8000/metrics

# Interface web do Prometheus
http://localhost:9091
```

---

## Variáveis de Ambiente

Arquivo `.env` na raiz do projeto:

```dotenv
# Banco de Dados
DB_HOST=localhost          # host do PostgreSQL
DB_PORT=5433               # porta (5433 com Docker, 5432 sem Docker)
DB_NAME=receita_db         # nome do banco
DB_USER=seu_usuario        # usuário
DB_PASS=sua_senha          # senha

# Performance — ajustar conforme hardware
CHUNK_SIZE=500000          # linhas por chunk no Parquet (reduzir se faltar RAM)
MAX_DOWNLOADS=8            # downloads paralelos simultâneos
MAX_WORKERS=10             # workers CPU para processamento paralelo
POSTGRES_POOL_SIZE=16      # pool de conexões SQLAlchemy
POSTGRES_MAX_OVERFLOW=32   # conexões extras além do pool

# Monitoramento
PROMETHEUS_PORT=8000       # porta do endpoint /metrics

# Receita Federal
RECEITA_BASE_URL=https://arquivos.receitafederal.gov.br/index.php/s/YggdBLfdninEJX9
RECEITA_TARGET_DIR=2026-03 # pasta do mês de referência no portal
```

### Ajuste de performance por hardware

| RAM disponível | CHUNK_SIZE recomendado | MAX_WORKERS |
|---|---|---|
| 16GB | 100000 | 4 |
| 32GB | 250000 | 6 |
| 48GB+ | 500000 | 10 |

---

## Troubleshooting

### PostgreSQL não conecta

```bash
# Verificar se o container está rodando
docker-compose ps

# Ver logs do banco
docker-compose logs postgres_receita

# Testar conexão manual
docker-compose exec postgres_receita psql -U admin_receita -d receita_db -c "SELECT 1;"

# Reiniciar o banco
docker-compose restart postgres_receita
```

### Exportação sem MEI nos CSVs

A tabela `empresas` pode estar com carga incompleta (apenas metade dos arquivos `Empresas0-9.parquet` carregados). O exportador usa `LEFT JOIN` em `empresas` e identifica MEI via tabela `simples`, então MEI funciona mesmo com `empresas` incompleta. Para corrigir `razao_social` de empresas novas, rode o pipeline completo novamente.

### Erro de memória durante transformação

Reduza o `CHUNK_SIZE` no `.env`:

```dotenv
CHUNK_SIZE=100000
```

### Erro de encoding no Windows (UnicodeEncodeError)

O pipeline já configura `chcp 65001` automaticamente no Windows. Se ainda ocorrer, verifique se o terminal está em UTF-8:

```powershell
chcp 65001
py app_entrypoint.py
```

### Download travado ou lento

Reduza o número de downloads paralelos no `.env`:

```dotenv
MAX_DOWNLOADS=4
```

### Verificar integridade dos dados no banco

```sql
-- Conectar ao banco
docker-compose exec postgres_receita psql -U admin_receita -d receita_db

-- Contar registros por tabela
SELECT 'empresas' as tabela, COUNT(*) FROM empresas
UNION ALL SELECT 'estabelecimentos', COUNT(*) FROM estabelecimentos
UNION ALL SELECT 'simples', COUNT(*) FROM simples;

-- Verificar MEI por ano (Nordeste)
SELECT SUBSTRING(est.data_inicio_atividade, 1, 4) AS ano, COUNT(*) AS total_mei
FROM estabelecimentos est
JOIN simples s ON est.cnpj_basico = s.cnpj_basico
WHERE est.uf IN ('AL','BA','CE','MA','PB','PE','PI','RN','SE')
  AND s.opcao_pelo_mei = 'S'
  AND s.data_exclusao_mei = '00000000'
  AND est.data_inicio_atividade >= '20230101'
GROUP BY 1 ORDER BY 1;
```

### Limpar tudo e recomeçar

```bash
# Para e remove containers + volumes (apaga o banco)
docker-compose down -v

# Remove dados processados
rm -rf data/raw_zips/* data/silver_parquet/*

# Sobe novamente
docker-compose up -d
py app_entrypoint.py
```

---

## Fonte dos Dados

Os dados são públicos e disponibilizados pela Receita Federal do Brasil:

- Portal: https://dados.gov.br/dados/conjuntos-dados/cadastro-nacional-da-pessoa-juridica---cnpj
- Atualização: mensal
- Formato original: CSV comprimido em ZIP
- Licença: Dados Abertos (Lei de Acesso à Informação)
