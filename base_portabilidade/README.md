# Base de Portabilidade

Esta pasta contém os dados de portabilidade telefônica e prefixos de operadoras.

## Arquivos

- `prefixos_operadora.json` - Mapeamento de prefixos telefônicos para operadoras
- `portabilidade.db` - Banco SQLite com dados de portabilidade (não versionado - ~1.9GB)
- `portabilidade.duckdb` - Banco DuckDB alternativo (não versionado)

## Observações

Os arquivos `.db`, `.db-shm`, `.db-wal` e `.duckdb` são bancos de dados locais 
e **não devem ser versionados** no Git devido ao tamanho e natureza binária.

Estes arquivos são gerados/atualizados localmente pelo sistema de processamento
de portabilidade telefônica.
