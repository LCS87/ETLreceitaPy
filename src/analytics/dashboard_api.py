"""
Dashboard API - API Flask para servir dados do analytics
Autor: Sistema ETL Receita
Data: 2026-04-20
"""

from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
from sqlalchemy import create_engine, text
from pathlib import Path
import json
from datetime import datetime

from src.utils.env_loader import config
from src.utils.log_handler import logger

app = Flask(__name__, 
    template_folder='dashboard_templates',
    static_folder='dashboard_static'
)
CORS(app)

# Conexão com banco
def get_engine():
    return create_engine(
        config.DATABASE_URL,
        connect_args={'sslmode': 'disable'},
        pool_size=5,
        max_overflow=10
    )

@app.route('/')
def index():
    """Página principal do dashboard"""
    return render_template('index.html')@app.route('/api/resumo-geral')
def resumo_geral():
    """Retorna resumo geral dos dados"""
    regiao = request.args.get('regiao')
    try:
        engine = get_engine()
        with engine.connect() as conn:
            # Total de empresas
            result = conn.execute(text("""
                SELECT 
                    SUM(f.qtd_empresas_ativas) as total_empresas,
                    SUM(f.qtd_empresas_novas) as total_novas,
                    AVG(f.score_potencial_banda_larga) as avg_score_bl,
                    AVG(f.score_potencial_telefonia) as avg_score_tel,
                    SUM(f.total_funcionarios_estimado) as total_funcionarios
                FROM analytics.fato_empresas f
                JOIN analytics.dim_localizacao l ON f.id_localizacao = l.id_localizacao
                WHERE f.id_tempo = (SELECT MAX(id_tempo) FROM analytics.fato_empresas)
                  AND (:regiao IS NULL OR l.regiao = :regiao)
            """), {"regiao": regiao})
            row = result.fetchone()
            
            return jsonify({
                'total_empresas': int(row[0] or 0),
                'total_novas': int(row[1] or 0),
                'avg_score_banda_larga': round(float(row[2] or 0), 2),
                'avg_score_telefonia': round(float(row[3] or 0), 2),
                'total_funcionarios': int(row[4] or 0)
            })
    except Exception as e:
        logger.error(f"Erro em resumo_geral: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/por-estado')
def por_estado():
    """Retorna dados por estado para mapa de calor e barras"""
    regiao = request.args.get('regiao')
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    l.uf,
                    l.nome_estado,
                    l.regiao,
                    l.latitude,
                    l.longitude,
                    SUM(f.qtd_empresas_ativas) as total_empresas,
                    SUM(f.qtd_empresas_novas) as novas_empresas,
                    SUM(CASE WHEN te.categoria = 'MEI' THEN f.qtd_empresas_ativas ELSE 0 END) as total_mei,
                    SUM(CASE WHEN te.categoria = 'LTDA' THEN f.qtd_empresas_ativas ELSE 0 END) as total_ltda,
                    SUM(CASE WHEN te.categoria = 'ME' THEN f.qtd_empresas_ativas ELSE 0 END) as total_me,
                    AVG(f.score_potencial_banda_larga) as score_bl,
                    AVG(f.score_potencial_telefonia) as score_tel,
                    SUM(f.total_funcionarios_estimado) as funcionarios
                FROM analytics.fato_empresas f
                JOIN analytics.dim_localizacao l ON f.id_localizacao = l.id_localizacao
                LEFT JOIN analytics.dim_tipo_empresa te ON f.id_tipo_empresa = te.id_tipo_empresa
                WHERE f.id_tempo = (SELECT MAX(id_tempo) FROM analytics.fato_empresas)
                  AND (:regiao IS NULL OR l.regiao = :regiao)
                GROUP BY l.uf, l.nome_estado, l.regiao, l.latitude, l.longitude
                ORDER BY total_empresas DESC
            """), {"regiao": regiao})
            
            data = []
            for row in result:
                data.append({
                    'uf': row[0],
                    'nome_estado': row[1],
                    'regiao': row[2],
                    'lat': float(row[3]) if row[3] else None,
                    'lng': float(row[4]) if row[4] else None,
                    'total_empresas': int(row[5]),
                    'novas_empresas': int(row[6]),
                    'total_mei': int(row[7]),
                    'total_ltda': int(row[8]),
                    'total_me': int(row[9]),
                    'score_banda_larga': round(float(row[10]), 2),
                    'score_telefonia': round(float(row[11]), 2),
                    'funcionarios': int(row[12])
                })
            
            return jsonify(data)
    except Exception as e:
        logger.error(f"Erro em por_estado: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/evolucao-mensal')
def evolucao_mensal():
    """Retorna evolução mensal para gráfico de linha"""
    regiao = request.args.get('regiao')
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    t.ano_mes,
                    t.nome_mes,
                    t.ano,
                    SUM(f.qtd_empresas_ativas) as total_empresas,
                    SUM(f.qtd_empresas_novas) as novas_empresas,
                    SUM(CASE WHEN te.categoria = 'MEI' THEN f.qtd_empresas_ativas ELSE 0 END) as total_mei,
                    SUM(CASE WHEN te.categoria = 'LTDA' THEN f.qtd_empresas_ativas ELSE 0 END) as total_ltda,
                    SUM(CASE WHEN te.categoria = 'ME' THEN f.qtd_empresas_ativas ELSE 0 END) as total_me
                FROM analytics.fato_empresas f
                JOIN analytics.dim_tempo t ON f.id_tempo = t.id_tempo
                JOIN analytics.dim_localizacao l ON f.id_localizacao = l.id_localizacao
                LEFT JOIN analytics.dim_tipo_empresa te ON f.id_tipo_empresa = te.id_tipo_empresa
                WHERE (:regiao IS NULL OR l.regiao = :regiao)
                GROUP BY t.ano_mes, t.nome_mes, t.ano
                ORDER BY t.ano, t.ano_mes
            """), {"regiao": regiao})
            
            data = []
            for row in result:
                data.append({
                    'ano_mes': row[0],
                    'nome_mes': row[1],
                    'ano': int(row[2]),
                    'total_empresas': int(row[3]),
                    'novas_empresas': int(row[4]),
                    'mei': int(row[5]),
                    'ltda': int(row[6]),
                    'me': int(row[7])
                })
            
            return jsonify(data)
    except Exception as e:
        logger.error(f"Erro em evolucao_mensal: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/por-tipo')
def por_tipo():
    """Retorna distribuição por tipo de empresa"""
    regiao = request.args.get('regiao')
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    te.categoria,
                    SUM(f.qtd_empresas_ativas) as quantidade,
                    AVG(f.score_potencial_banda_larga) as avg_score_bl,
                    AVG(f.score_potencial_telefonia) as avg_score_tel,
                    SUM(f.total_funcionarios_estimado) as funcionarios
                FROM analytics.fato_empresas f
                JOIN analytics.dim_tipo_empresa te ON f.id_tipo_empresa = te.id_tipo_empresa
                JOIN analytics.dim_localizacao l ON f.id_localizacao = l.id_localizacao
                WHERE f.id_tempo = (SELECT MAX(id_tempo) FROM analytics.fato_empresas)
                  AND (:regiao IS NULL OR l.regiao = :regiao)
                GROUP BY te.categoria
                ORDER BY quantidade DESC
            """), {"regiao": regiao})
            
            data = []
            for row in result:
                data.append({
                    'categoria': row[0],
                    'quantidade': int(row[1]),
                    'score_banda_larga': round(float(row[2]), 2),
                    'score_telefonia': round(float(row[3]), 2),
                    'funcionarios': int(row[4])
                })
            
            return jsonify(data)
    except Exception as e:
        logger.error(f"Erro em por_tipo: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/mapa-tipo-estado')
def mapa_tipo_estado():
    """Retorna dados para mapa de calor: tipo de empresa por estado"""
    regiao = request.args.get('regiao')
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    l.uf,
                    l.nome_estado,
                    te.categoria,
                    SUM(f.qtd_empresas_ativas) as quantidade,
                    SUM(f.qtd_empresas_ativas) * 100.0 / NULLIF(
                        SUM(SUM(f.qtd_empresas_ativas)) OVER (PARTITION BY l.uf), 0
                    ) as percentual
                FROM analytics.fato_empresas f
                JOIN analytics.dim_localizacao l ON f.id_localizacao = l.id_localizacao
                JOIN analytics.dim_tipo_empresa te ON f.id_tipo_empresa = te.id_tipo_empresa
                WHERE f.id_tempo = (SELECT MAX(id_tempo) FROM analytics.fato_empresas)
                  AND (:regiao IS NULL OR l.regiao = :regiao)
                GROUP BY l.uf, l.nome_estado, te.categoria
                ORDER BY l.uf, quantidade DESC
            """), {"regiao": regiao})
            
            data = {}
            for row in result:
                uf = row[0]
                if uf not in data:
                    data[uf] = {
                        'uf': uf,
                        'nome_estado': row[1],
                        'tipos': {}
                    }
                data[uf]['tipos'][row[2]] = {
                    'quantidade': int(row[3]),
                    'percentual': round(float(row[4]), 2)
                }
            
            return jsonify(list(data.values()))
    except Exception as e:
        logger.error(f"Erro em mapa_tipo_estado: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/potencial-comercial')
def potencial_comercial():
    """Retorna métricas de potencial comercial por estado"""
    regiao = request.args.get('regiao')
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    l.uf,
                    l.nome_estado,
                    SUM(f.qtd_empresas_tecnologia) as empresas_tecnologia,
                    SUM(f.qtd_empresas_servicos) as empresas_servicos,
                    SUM(f.qtd_empresas_comercio) as empresas_comercio,
                    SUM(f.total_funcionarios_estimado) as funcionarios_total,
                    AVG(f.score_potencial_banda_larga) as score_banda_larga,
                    AVG(f.score_potencial_telefonia) as score_telefonia,
                    (SUM(f.qtd_empresas_tecnologia) * AVG(f.score_potencial_banda_larga) / 100)::INT as potencial_estimado
                FROM analytics.fato_empresas f
                JOIN analytics.dim_localizacao l ON f.id_localizacao = l.id_localizacao
                WHERE f.id_tempo = (SELECT MAX(id_tempo) FROM analytics.fato_empresas)
                  AND (:regiao IS NULL OR l.regiao = :regiao)
                GROUP BY l.uf, l.nome_estado
                ORDER BY potencial_estimado DESC
            """), {"regiao": regiao})
            
            data = []
            for row in result:
                data.append({
                    'uf': row[0],
                    'nome_estado': row[1],
                    'empresas_tecnologia': int(row[2]),
                    'empresas_servicos': int(row[3]),
                    'empresas_comercio': int(row[4]),
                    'funcionarios': int(row[5]),
                    'score_banda_larga': round(float(row[6]), 2),
                    'score_telefonia': round(float(row[7]), 2),
                    'potencial_estimado': int(row[8])
                })
            
            return jsonify(data)
    except Exception as e:
        logger.error(f"Erro em potencial_comercial: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/crescimento-por-estado')
def crescimento_por_estado():
    """Retorna crescimento mensal por estado"""
    regiao = request.args.get('regiao')
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT 
                    l.uf,
                    l.nome_estado,
                    t.ano_mes,
                    e.qtd_ltda,
                    e.qtd_mei,
                    e.qtd_me,
                    e.crescimento_ltda,
                    e.crescimento_mei,
                    e.crescimento_me,
                    e.crescimento_total
                FROM analytics.fato_evolucao_mensal e
                JOIN analytics.dim_localizacao l ON e.id_localizacao = l.id_localizacao
                JOIN analytics.dim_tempo t ON e.id_tempo = t.id_tempo
                WHERE e.crescimento_total != 0
                  AND (:regiao IS NULL OR l.regiao = :regiao)
                ORDER BY l.uf, t.ano_mes
            """), {"regiao": regiao})
            
            data = {}
            for row in result:
                uf = row[0]
                if uf not in data:
                    data[uf] = {
                        'uf': uf,
                        'nome_estado': row[1],
                        'evolucao': []
                    }
                data[uf]['evolucao'].append({
                    'ano_mes': row[2],
                    'qtd_ltda': int(row[3]),
                    'qtd_mei': int(row[4]),
                    'qtd_me': int(row[5]),
                    'crescimento_ltda': round(float(row[6]), 2),
                    'crescimento_mei': round(float(row[7]), 2),
                    'crescimento_me': round(float(row[8]), 2),
                    'crescimento_total': round(float(row[9]), 2)
                })
            
            return jsonify(list(data.values()))
    except Exception as e:
        logger.error(f"Erro em crescimento_por_estado: {e}")
        return jsonify({'error': str(e)}), 500)}), 500

@app.route('/api/atualizar-dados', methods=['POST'])
def atualizar_dados():
    """Endpoint para atualizar dados do analytics (chama o processor)"""
    try:
        from src.analytics.analytics_processor import AnalyticsProcessor
        
        processor = AnalyticsProcessor()
        ano_mes = request.json.get('ano_mes') if request.json else None
        
        resultado = processor.executar_pipeline_analytics(ano_mes)
        
        return jsonify({
            'status': 'success',
            'message': 'Dados atualizados com sucesso',
            'resultado': resultado
        })
    except Exception as e:
        logger.error(f"Erro em atualizar_dados: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    print("=== Dashboard API - Analytics Receita ===")
    print(f"Acesse: http://localhost:5001")
    print(f"API Docs:")
    print(f"  - /api/resumo-geral")
    print(f"  - /api/por-estado")
    print(f"  - /api/evolucao-mensal")
    print(f"  - /api/por-tipo")
    print(f"  - /api/mapa-tipo-estado")
    print(f"  - /api/potencial-comercial")
    print(f"  - /api/crescimento-por-estado")
    print()
    
    app.run(host='0.0.0.0', port=5001, debug=True)
