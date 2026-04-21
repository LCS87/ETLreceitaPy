#!/usr/bin/env python3
"""
Script de execução do Dashboard Analytics
Autor: Sistema ETL Receita
Data: 2026-04-20

Uso:
    python run_dashboard.py              # Inicia apenas o dashboard (modo PostgreSQL)
    python run_dashboard.py --direct     # Inicia dashboard direto (sem PostgreSQL, usa Parquets)
    python run_dashboard.py --setup      # Cria schema e popula dados
    python run_dashboard.py --update     # Atualiza dados do analytics
    python run_dashboard.py --full       # Setup + Update + Run (modo completo)
"""

import argparse
import sys
import os
from pathlib import Path

# Configura encoding UTF-8 para suporte a emojis no Windows
os.environ['PYTHONIOENCODING'] = 'utf-8'
if sys.platform == 'win32':
    os.system('chcp 65001 > nul')
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Adiciona src ao path
sys.path.insert(0, str(Path(__file__).parent))


def setup_database():
    """Cria schema e tabelas do analytics"""
    print("=== CONFIGURANDO BANCO DE DADOS ANALYTICS ===")
    
    from sqlalchemy import create_engine, text
    from src.utils.env_loader import config
    
    engine = create_engine(
        config.DATABASE_URL,
        connect_args={'sslmode': 'disable'}
    )
    
    # Lê e executa o script SQL
    schema_path = Path(__file__).parent / 'src' / 'analytics' / 'schema_analytics.sql'
    
    with open(schema_path, 'r', encoding='utf-8') as f:
        sql_script = f.read()
    
    with engine.connect() as conn:
        # Executa comandos separadamente (PostgreSQL não suporta múltiplos comandos em uma string com psycopg2)
        commands = sql_script.split(';')
        
        for cmd in commands:
            cmd = cmd.strip()
            if cmd and not cmd.startswith('--'):
                try:
                    conn.execute(text(cmd))
                    conn.commit()
                except Exception as e:
                    print(f"  Aviso (comando ignorado): {e}")
    
    print("✅ Schema analytics criado com sucesso!")


def update_data(ano_mes=None):
    """Executa o processor para popular dados"""
    print("=== ATUALIZANDO DADOS DO ANALYTICS ===")
    
    from src.analytics.analytics_processor import AnalyticsProcessor
    
    processor = AnalyticsProcessor()
    resultado = processor.executar_pipeline_analytics(ano_mes)
    
    print(f"\n✅ Dados atualizados!")
    print(f"   - Empresas processadas: {resultado['empresas_processadas']:,}")
    print(f"   - Estabelecimentos ativos: {resultado['estabelecimentos_ativos']:,}")
    print(f"   - Estados cobertos: {resultado['estados_cobertos']}")


def run_dashboard(direct_mode=False):
    """Inicia o servidor web do dashboard"""
    print("=== INICIANDO DASHBOARD ANALYTICS ===")
    print()
    print("📊 Dashboard disponível em: http://localhost:5001")
    print("📡 API endpoints:")
    print("   - http://localhost:5001/api/resumo-geral")
    print("   - http://localhost:5001/api/por-estado")
    print("   - http://localhost:5001/api/evolucao-mensal")
    print("   - http://localhost:5001/api/por-tipo")
    print("   - http://localhost:5001/api/mapa-tipo-estado")
    print("   - http://localhost:5001/api/potencial-comercial")
    print("   - http://localhost:5001/api/crescimento-por-estado")
    print()
    print("Pressione CTRL+C para parar")
    print()
    
    if direct_mode:
        print("📁 Modo direto: processando dados dos Parquets...")
        from src.analytics.dashboard_direct import app, processor
        processor.process_all()
    else:
        print("🐘 Modo PostgreSQL: conectando ao banco...")
        from src.analytics.dashboard_api import app
    
    app.run(host='0.0.0.0', port=5001, debug=False)


def main():
    parser = argparse.ArgumentParser(
        description='Dashboard Analytics - Empresas Receita Federal'
    )
    parser.add_argument(
        '--setup',
        action='store_true',
        help='Cria schema e tabelas no banco de dados'
    )
    parser.add_argument(
        '--update',
        action='store_true',
        help='Processa dados e popula tabelas analytics'
    )
    parser.add_argument(
        '--full',
        action='store_true',
        help='Setup + Update + Run (modo completo)'
    )
    parser.add_argument(
        '--direct',
        action='store_true',
        help='Usa modo direto (Parquet) em vez de PostgreSQL'
    )
    parser.add_argument(
        '--ano-mes',
        type=str,
        default=None,
        help='Ano-mês para processar (formato: YYYY-MM)'
    )
    
    args = parser.parse_args()
    
    if args.full:
        setup_database()
        update_data(args.ano_mes)
        run_dashboard(direct_mode=False)
    elif args.setup:
        setup_database()
    elif args.update:
        update_data(args.ano_mes)
    else:
        run_dashboard(direct_mode=args.direct)


if __name__ == '__main__':
    main()
