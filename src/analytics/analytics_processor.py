"""
Analytics Processor - Processa dados dos Parquets para tabelas analíticas
Autor: Sistema ETL Receita
Data: 2026-04-20

Este módulo extrai métricas dos dados Parquet e popula o schema analytics
para geração de dashboards e relatórios de vendas.
"""

import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path
from sqlalchemy import create_engine, text
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import logging

from src.utils.env_loader import config
from src.utils.log_handler import logger


@dataclass
class MetricasEmpresa:
    """Estrutura para métricas de uma empresa"""
    uf: str
    cnpj_basico: str
    razao_social: str
    natureza_juridica: str
    porte: Optional[str] = None
    categoria: Optional[str] = None  # LTDA, MEI, ME, etc
    situacao: str = '02'  # 02 = Ativa
    data_inicio_atividade: Optional[str] = None
    cnae_fiscal: Optional[str] = None
    municipio: Optional[str] = None
    ddd1: Optional[str] = None
    telefone1: Optional[str] = None


class AnalyticsProcessor:
    """
    Processador de dados para analytics.
    Extrai métricas dos arquivos Parquet e popula tabelas analíticas.
    """
    
    # Mapeamento de natureza jurídica para categoria
    NATUREZA_TO_CATEGORIA = {
        # LTDA
        '2062': 'LTDA', '2305': 'LTDA',
        # MEI
        '2135': 'MEI',
        # ME (Empresário Individual)
        '2313': 'ME',
        # EIRELI
        '2214': 'EIRELI',
        # SA
        '2046': 'SA', '2254': 'SA',
        # Outros
        '1015': 'EI', '1040': 'EI', '1104': 'EI',  # Pessoa Física/Empresário
    }
    
    # CNAEs relacionados a tecnologia/telecom (para potencial de vendas)
    CNAE_TECNOLOGIA = [
        '61',    # Telecomunicações
        '62',    # Programação, consultoria
        '63',    # Portais, provedores
        '465',   # Comércio atacadista de equipamentos de informática
        '474',   # Comércio varejista de equipamentos de informática
        '951',   # Reparação de equipamentos de comunicação
        '952',   # Reparação de equipamentos de informática
    ]
    
    # CNAEs de serviços (alto potencial)
    CNAE_SERVICOS = [
        '69',    # Atividades jurídicas, contábeis
        '70',    # Atividades de sedes administrativas
        '71',    # Serviços técnicos
        '73',    # Publicidade
        '74',    # Outras atividades profissionais
    ]
    
    # CNAEs de comércio
    CNAE_COMERCIO = [
        '45', '46', '47',  # Comércio veículos, atacadista, varejista
    ]
    
    def __init__(self, db_config: Optional[str] = None):
        """Inicializa o processador com conexão ao banco"""
        self.url = db_config if db_config else config.DATABASE_URL
        self.engine = create_engine(
            self.url,
            connect_args={'sslmode': 'disable'},
            pool_size=5,
            max_overflow=10
        )
        self.silver_dir = Path(config.SILVER_DIR)
        
    def _classificar_empresa(self, natureza_juridica: str, cnae: Optional[str] = None) -> Tuple[str, str]:
        """
        Classifica empresa por tipo e porte
        Retorna: (categoria, porte)
        """
        natureza = str(natureza_juridica).strip()
        
        # Verifica MEI primeiro
        if natureza == '2135':
            return ('MEI', 'MEI')
        
        # Classifica por natureza
        categoria = self.NATUREZA_TO_CATEGORIA.get(natureza, 'OUTROS')
        
        # Determina porte baseado no CNAE (simplificado)
        # Na prática, usaria faturamento ou número de funcionários
        porte = 'DEMAIS'
        if cnae:
            cnae_str = str(cnae)[:2]
            if categoria == 'MEI':
                porte = 'MEI'
            elif cnae_str in ['47', '56']:  # Comércio varejista, alimentação
                porte = 'ME'
        
        return (categoria, porte)
    
    def _calcular_score_potencial(self, cnae: Optional[str], categoria: str) -> Tuple[float, float]:
        """
        Calcula score de potencial para venda (0-100)
        Retorna: (score_banda_larga, score_telefonia)
        """
        if not cnae:
            return (30.0, 25.0)  # Score base
        
        cnae_str = str(cnae)
        cnae_prefix = cnae_str[:2] if len(cnae_str) >= 2 else cnae_str
        
        # Score base por tipo de empresa
        scores_base = {
            'LTDA': (85.0, 80.0),
            'MEI': (40.0, 50.0),
            'ME': (60.0, 65.0),
            'SA': (95.0, 90.0),
            'EIRELI': (75.0, 70.0),
            'OUTROS': (50.0, 45.0),
        }
        
        score_bl, score_tel = scores_base.get(categoria, (50.0, 45.0))
        
        # Ajustes por CNAE
        if any(cnae_str.startswith(c) for c in self.CNAE_TECNOLOGIA):
            score_bl += 15  # Tecnologia = mais banda larga
            score_tel += 10
        
        if any(cnae_str.startswith(c) for c in self.CNAE_SERVICOS):
            score_bl += 10  # Serviços = necessidade de comunicação
            score_tel += 15
        
        if any(cnae_str.startswith(c) for c in self.CNAE_COMERCIO):
            score_tel += 10  # Comércio = telefonia
        
        # Limita a 100
        return (min(score_bl, 100.0), min(score_tel, 100.0))
    
    def _estimar_funcionarios(self, categoria: str, porte: str) -> int:
        """Estima número de funcionários baseado no porte"""
        estimativas = {
            'MEI': 1,
            'ME': 5,
            'EPP': 15,
            'DEMAIS': 50,
        }
        return estimativas.get(porte, 10)
    
    def _is_tecnologia(self, cnae: Optional[str]) -> bool:
        """Verifica se é empresa de tecnologia"""
        if not cnae:
            return False
        return any(str(cnae).startswith(c) for c in self.CNAE_TECNOLOGIA)
    
    def _is_servicos(self, cnae: Optional[str]) -> bool:
        """Verifica se é empresa de serviços"""
        if not cnae:
            return False
        return any(str(cnae).startswith(c) for c in self.CNAE_SERVICOS)
    
    def _is_comercio(self, cnae: Optional[str]) -> bool:
        """Verifica se é empresa de comércio"""
        if not cnae:
            return False
        return any(str(cnae).startswith(c) for c in self.CNAE_COMERCIO)
    
    def processar_empresas(self, ano_mes: str = None) -> Dict:
        """
        Processa arquivo de empresas e extrai métricas
        """
        if not ano_mes:
            ano_mes = datetime.now().strftime('%Y-%m')
        
        logger.info(f"--- Processando métricas de empresas para {ano_mes} ---")
        
        # Encontra arquivo de empresas
        empresas_files = list(self.silver_dir.glob("Empresas*.parquet"))
        if not empresas_files:
            logger.warning("Nenhum arquivo Empresas*.parquet encontrado")
            return {}
        
        metrics = {
            'total_processado': 0,
            'por_uf': {},
            'por_tipo': {},
            'por_categoria': {},
        }
        
        for file in empresas_files:
            logger.info(f"Processando: {file.name}")
            
            try:
                # Lê arquivo em chunks para economia de memória
                parquet_file = pq.ParquetFile(file)
                
                for batch in parquet_file.iter_batches(batch_size=100000):
                    df = batch.to_pandas()
                    
                    # Classifica cada empresa
                    for _, row in df.iterrows():
                        natureza = str(row.get('natureza_juridica', '')).strip()
                        cnae = str(row.get('cnae_fiscal', '')) if pd.notna(row.get('cnae_fiscal')) else None
                        
                        categoria, porte = self._classificar_empresa(natureza, cnae)
                        score_bl, score_tel = self._calcular_score_potencial(cnae, categoria)
                        func_estimado = self._estimar_funcionarios(categoria, porte)
                        
                        # Acumula métricas
                        uf = str(row.get('uf', 'XX'))
                        if uf not in metrics['por_uf']:
                            metrics['por_uf'][uf] = {
                                'total': 0, 'mei': 0, 'ltda': 0, 'me': 0,
                                'score_bl': 0, 'score_tel': 0, 'funcionarios': 0
                            }
                        
                        metrics['por_uf'][uf]['total'] += 1
                        metrics['por_uf'][uf]['score_bl'] += score_bl
                        metrics['por_uf'][uf]['score_tel'] += score_tel
                        metrics['por_uf'][uf]['funcionarios'] += func_estimado
                        
                        if categoria == 'MEI':
                            metrics['por_uf'][uf]['mei'] += 1
                        elif categoria == 'LTDA':
                            metrics['por_uf'][uf]['ltda'] += 1
                        elif categoria == 'ME':
                            metrics['por_uf'][uf]['me'] += 1
                        
                        metrics['total_processado'] += 1
                
            except Exception as e:
                logger.error(f"Erro processando {file.name}: {e}")
                continue
        
        # Calcula médias
        for uf in metrics['por_uf']:
            total = metrics['por_uf'][uf]['total']
            if total > 0:
                metrics['por_uf'][uf]['score_bl'] /= total
                metrics['por_uf'][uf]['score_tel'] /= total
        
        logger.info(f"Total processado: {metrics['total_processado']:,} empresas")
        return metrics
    
    def processar_estabelecimentos(self, ano_mes: str = None) -> Dict:
        """
        Processa arquivo de estabelecimentos para métricas detalhadas
        """
        if not ano_mes:
            ano_mes = datetime.now().strftime('%Y-%m')
        
        logger.info(f"--- Processando métricas de estabelecimentos para {ano_mes} ---")
        
        estab_files = list(self.silver_dir.glob("Estabelecimentos*.parquet"))
        if not estab_files:
            logger.warning("Nenhum arquivo Estabelecimentos*.parquet encontrado")
            return {}
        
        metrics = {
            'total_ativos': 0,
            'por_uf': {},
            'por_cnae': {},
        }
        
        for file in estab_files:
            logger.info(f"Processando: {file.name}")
            
            try:
                parquet_file = pq.ParquetFile(file)
                
                for batch in parquet_file.iter_batches(batch_size=100000):
                    df = batch.to_pandas()
                    
                    # Filtra apenas ativos (situacao_cadastral = 02)
                    df_ativos = df[df['situacao_cadastral'] == '02']
                    
                    for _, row in df_ativos.iterrows():
                        uf = str(row.get('uf', 'XX'))
                        cnae = str(row.get('cnae_fiscal_principal', ''))[:2]
                        
                        if uf not in metrics['por_uf']:
                            metrics['por_uf'][uf] = {
                                'ativos': 0, 'tecnologia': 0, 'servicos': 0, 'comercio': 0
                            }
                        
                        metrics['por_uf'][uf]['ativos'] += 1
                        
                        if cnae in self.CNAE_TECNOLOGIA:
                            metrics['por_uf'][uf]['tecnologia'] += 1
                        elif cnae in self.CNAE_SERVICOS:
                            metrics['por_uf'][uf]['servicos'] += 1
                        elif cnae in self.CNAE_COMERCIO:
                            metrics['por_uf'][uf]['comercio'] += 1
                        
                        metrics['total_ativos'] += 1
                        
            except Exception as e:
                logger.error(f"Erro processando {file.name}: {e}")
                continue
        
        logger.info(f"Total ativos: {metrics['total_ativos']:,} estabelecimentos")
        return metrics
    
    def _get_id_tempo(self, ano_mes: str) -> int:
        """Busca ou cria id_tempo para o período"""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT id_tempo FROM analytics.dim_tempo WHERE ano_mes = :ano_mes"),
                {'ano_mes': ano_mes}
            )
            row = result.fetchone()
            if row:
                return row[0]
            
            # Cria novo período
            ano, mes = map(int, ano_mes.split('-'))
            conn.execute(
                text("""
                    INSERT INTO analytics.dim_tempo (ano, mes, trimestre, ano_mes, nome_mes)
                    VALUES (:ano, :mes, :trimestre, :ano_mes, :nome_mes)
                    RETURNING id_tempo
                """),
                {
                    'ano': ano, 'mes': mes,
                    'trimestre': ((mes - 1) // 3) + 1,
                    'ano_mes': ano_mes,
                    'nome_mes': datetime(ano, mes, 1).strftime('%B')
                }
            )
            conn.commit()
            
            result = conn.execute(
                text("SELECT id_tempo FROM analytics.dim_tempo WHERE ano_mes = :ano_mes"),
                {'ano_mes': ano_mes}
            )
            return result.fetchone()[0]
    
    def _get_id_localizacao(self, uf: str) -> int:
        """Busca id_localizacao pela UF"""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT id_localizacao FROM analytics.dim_localizacao WHERE uf = :uf"),
                {'uf': uf}
            )
            row = result.fetchone()
            return row[0] if row else None
    
    def _get_id_tipo_empresa(self, categoria: str) -> int:
        """Busca ou cria id_tipo_empresa pela categoria"""
        with self.engine.connect() as conn:
            result = conn.execute(
                text("SELECT id_tipo_empresa FROM analytics.dim_tipo_empresa WHERE categoria = :categoria"),
                {'categoria': categoria}
            )
            row = result.fetchone()
            if row:
                return row[0]
            
            # Gera codigo_natureza único baseado na categoria
            codigo_map = {
                'LTDA': 'AUTO_LTDA', 'MEI': 'AUTO_MEI', 'ME': 'AUTO_ME',
                'SA': 'AUTO_SA', 'EIRELI': 'AUTO_EIR', 'EI': 'AUTO_EI',
                'OUTROS': 'AUTO_OUT'
            }
            codigo = codigo_map.get(categoria, f'AUTO_{categoria[:4]}')
            
            # Insere nova categoria
            conn.execute(
                text("""
                    INSERT INTO analytics.dim_tipo_empresa (codigo_natureza, descricao_natureza, categoria, porte)
                    VALUES (:codigo, :descricao, :categoria, :porte)
                    ON CONFLICT (codigo_natureza) DO NOTHING
                """),
                {
                    'codigo': codigo,
                    'descricao': f'Categoria {categoria}',
                    'categoria': categoria,
                    'porte': categoria
                }
            )
            conn.commit()
            
            result = conn.execute(
                text("SELECT id_tipo_empresa FROM analytics.dim_tipo_empresa WHERE categoria = :categoria"),
                {'categoria': categoria}
            )
            return result.fetchone()[0]
    
    def inserir_fato_empresas(self, metrics_empresas: Dict, metrics_estabs: Dict, ano_mes: str):
        """Insere dados na tabela fato_empresas"""
        logger.info("--- Inserindo dados na tabela fato_empresas ---")
        
        id_tempo = self._get_id_tempo(ano_mes)
        
        with self.engine.connect() as conn:
            # Limpa dados existentes do período
            conn.execute(
                text("DELETE FROM analytics.fato_empresas WHERE id_tempo = :id_tempo"),
                {'id_tempo': id_tempo}
            )
            conn.commit()
            
            # Insere novos dados
            for uf, dados in metrics_empresas.get('por_uf', {}).items():
                id_localizacao = self._get_id_localizacao(uf)
                if not id_localizacao:
                    continue
                
                # Categorias: LTDA, MEI, ME
                for categoria, qtd in [('LTDA', dados.get('ltda', 0)), 
                                       ('MEI', dados.get('mei', 0)), 
                                       ('ME', dados.get('me', 0))]:
                    if qtd == 0:
                        continue
                    
                    id_tipo = self._get_id_tipo_empresa(categoria)
                    
                    # Dados complementares do estabelecimentos
                    estabs_uf = metrics_estabs.get('por_uf', {}).get(uf, {})
                    
                    conn.execute(
                        text("""
                            INSERT INTO analytics.fato_empresas 
                            (id_tempo, id_localizacao, id_tipo_empresa, 
                             qtd_empresas_ativas, qtd_empresas_novas, qtd_empresas_baixadas,
                             qtd_empresas_tecnologia, qtd_empresas_servicos, qtd_empresas_comercio,
                             score_potencial_banda_larga, score_potencial_telefonia,
                             total_funcionarios_estimado, media_funcionarios_por_empresa)
                            VALUES (:id_tempo, :id_localizacao, :id_tipo,
                                    :qtd_ativas, 0, 0,
                                    :qtd_tec, :qtd_svc, :qtd_com,
                                    :score_bl, :score_tel,
                                    :func_total, :func_media)
                            ON CONFLICT (id_tempo, id_localizacao, id_tipo_empresa) 
                            DO UPDATE SET
                                qtd_empresas_ativas = EXCLUDED.qtd_empresas_ativas,
                                score_potencial_banda_larga = EXCLUDED.score_potencial_banda_larga,
                                score_potencial_telefonia = EXCLUDED.score_potencial_telefonia,
                                total_funcionarios_estimado = EXCLUDED.total_funcionarios_estimado,
                                data_processamento = CURRENT_TIMESTAMP
                        """),
                        {
                            'id_tempo': id_tempo,
                            'id_localizacao': id_localizacao,
                            'id_tipo': id_tipo,
                            'qtd_ativas': qtd,
                            'qtd_tec': estabs_uf.get('tecnologia', 0),
                            'qtd_svc': estabs_uf.get('servicos', 0),
                            'qtd_com': estabs_uf.get('comercio', 0),
                            'score_bl': dados.get('score_bl', 50),
                            'score_tel': dados.get('score_tel', 45),
                            'func_total': dados.get('funcionarios', 0),
                            'func_media': dados.get('funcionarios', 0) / max(qtd, 1)
                        }
                    )
                
                conn.commit()
        
        logger.info("--- Dados inseridos com sucesso ---")
    
    def gerar_evolucao_mensal(self, ano_mes: str):
        """Gera tabela de evolução mensal comparando com mês anterior"""
        logger.info("--- Gerando evolução mensal ---")
        
        with self.engine.connect() as conn:
            # Calcula mês anterior
            ano, mes = map(int, ano_mes.split('-'))
            if mes == 1:
                mes_ant = 12
                ano_ant = ano - 1
            else:
                mes_ant = mes - 1
                ano_ant = ano
            
            ano_mes_ant = f"{ano_ant}-{mes_ant:02d}"
            
            # Insere evolução para cada estado
            conn.execute(text("""
                INSERT INTO analytics.fato_evolucao_mensal 
                (id_tempo, id_localizacao, qtd_ltda, qtd_mei, qtd_me, 
                 crescimento_ltda, crescimento_mei, crescimento_me, crescimento_total)
                SELECT 
                    t.id_tempo,
                    l.id_localizacao,
                    COALESCE(SUM(CASE WHEN te.categoria = 'LTDA' THEN f.qtd_empresas_ativas ELSE 0 END), 0) as qtd_ltda,
                    COALESCE(SUM(CASE WHEN te.categoria = 'MEI' THEN f.qtd_empresas_ativas ELSE 0 END), 0) as qtd_mei,
                    COALESCE(SUM(CASE WHEN te.categoria = 'ME' THEN f.qtd_empresas_ativas ELSE 0 END), 0) as qtd_me,
                    0, 0, 0, 0  -- crescimentos calculados posteriormente
                FROM analytics.dim_tempo t
                CROSS JOIN analytics.dim_localizacao l
                LEFT JOIN analytics.fato_empresas f ON t.id_tempo = f.id_tempo AND l.id_localizacao = f.id_localizacao
                LEFT JOIN analytics.dim_tipo_empresa te ON f.id_tipo_empresa = te.id_tipo_empresa
                WHERE t.ano_mes = :ano_mes
                GROUP BY t.id_tempo, l.id_localizacao
                ON CONFLICT (id_tempo, id_localizacao) DO NOTHING
            """), {'ano_mes': ano_mes})
            
            conn.commit()
            
            # Atualiza crescimentos comparando com mês anterior
            conn.execute(text("""
                UPDATE analytics.fato_evolucao_mensal e
                SET 
                    crescimento_ltda = CASE 
                        WHEN e_ant.qtd_ltda > 0 THEN ((e.qtd_ltda - e_ant.qtd_ltda)::DECIMAL / e_ant.qtd_ltda) * 100 
                        ELSE 0 
                    END,
                    crescimento_mei = CASE 
                        WHEN e_ant.qtd_mei > 0 THEN ((e.qtd_mei - e_ant.qtd_mei)::DECIMAL / e_ant.qtd_mei) * 100 
                        ELSE 0 
                    END,
                    crescimento_me = CASE 
                        WHEN e_ant.qtd_me > 0 THEN ((e.qtd_me - e_ant.qtd_me)::DECIMAL / e_ant.qtd_me) * 100 
                        ELSE 0 
                    END,
                    crescimento_total = CASE 
                        WHEN (e_ant.qtd_ltda + e_ant.qtd_mei + e_ant.qtd_me) > 0 
                        THEN (((e.qtd_ltda + e.qtd_mei + e.qtd_me) - (e_ant.qtd_ltda + e_ant.qtd_mei + e_ant.qtd_me))::DECIMAL / 
                              (e_ant.qtd_ltda + e_ant.qtd_mei + e_ant.qtd_me)) * 100 
                        ELSE 0 
                    END
                FROM analytics.fato_evolucao_mensal e_ant
                JOIN analytics.dim_tempo t ON e.id_tempo = t.id_tempo
                JOIN analytics.dim_tempo t_ant ON t_ant.ano_mes = :ano_mes_ant
                WHERE e_ant.id_tempo = t_ant.id_tempo AND e_ant.id_localizacao = e.id_localizacao
                AND t.ano_mes = :ano_mes
            """), {'ano_mes': ano_mes, 'ano_mes_ant': ano_mes_ant})
            
            conn.commit()
        
        logger.info("--- Evolução mensal gerada ---")
    
    def executar_pipeline_analytics(self, ano_mes: str = None):
        """
        Executa pipeline completo de analytics
        """
        if not ano_mes:
            ano_mes = datetime.now().strftime('%Y-%m')
        
        logger.info(f"=== INICIANDO PIPELINE ANALYTICS - {ano_mes} ===")
        
        # 1. Processa dados
        metrics_empresas = self.processar_empresas(ano_mes)
        metrics_estabs = self.processar_estabelecimentos(ano_mes)
        
        # 2. Insere no banco
        self.inserir_fato_empresas(metrics_empresas, metrics_estabs, ano_mes)
        
        # 3. Gera evolução mensal
        self.gerar_evolucao_mensal(ano_mes)
        
        logger.info(f"=== PIPELINE ANALYTICS CONCLUÍDO - {ano_mes} ===")
        
        return {
            'empresas_processadas': metrics_empresas.get('total_processado', 0),
            'estabelecimentos_ativos': metrics_estabs.get('total_ativos', 0),
            'estados_cobertos': len(metrics_empresas.get('por_uf', {}))
        }


if __name__ == "__main__":
    processor = AnalyticsProcessor()
    resultado = processor.executar_pipeline_analytics()
    print(f"Resultado: {resultado}")
