"""
Exportador otimizado com queries usando índices e segmentação mensal.
"""
import pandas as pd
from pathlib import Path
from datetime import datetime
from sqlalchemy import create_engine, text
from src.utils.env_loader import config
from src.utils.log_handler import logger

ANO_INICIO = 2023
ANO_FIM = datetime.now().year


class NordesteExporterOptimized:
    """Exportador com queries otimizadas e segmentação mensal"""

    def __init__(self, batch_size: int = 200000):
        self.engine = create_engine(config.DATABASE_URL)
        self.batch_size = batch_size
        self.export_paths = {
            'anual': Path(config.SILVER_DIR) / 'exports_final/1_Processo_Anual',
            'trimestral': Path(config.SILVER_DIR) / 'exports_final/2_Processo_Trimestral',
            'mensal': Path(config.SILVER_DIR) / 'exports_final/3_Processo_Mensal'
        }
        for path in self.export_paths.values():
            path.mkdir(parents=True, exist_ok=True)

    def export_from_db(self):
        """Executa exportacao completa com queries otimizadas"""
        import time
        import shutil
        from src.monitoring.prometheus_stats import metrics

        logger.info(f"Iniciando exportacao otimizada ({ANO_INICIO}-{ANO_FIM})...")

        # Limpa exports anteriores para evitar duplicatas
        for path in self.export_paths.values():
            if path.exists():
                shutil.rmtree(path)
            path.mkdir(parents=True, exist_ok=True)
        logger.info("Pastas de exportacao limpas.")

        # LEFT JOIN em empresas e simples — nao descarta registros sem match em empresas
        query = text(f"""
        SELECT
            est.cnpj_basico || est.cnpj_ordem || est.cnpj_dv AS cnpj_completo,
            COALESCE(emp.razao_social, est.nome_fantasia, '') AS razao_social,
            UPPER(
                est.logradouro || ', ' ||
                COALESCE(NULLIF(est.numero, ''), 'SN') || ', ' ||
                COALESCE(NULLIF(est.complemento, ''), '') || ', ' ||
                est.bairro || ', ' ||
                est.uf || ', ' ||
                est.cep
            ) AS endereco_completo,
            est.correio_eletronico AS email,
            est.data_inicio_atividade,
            est.uf,
            est.telefone,
            est.operadora,
            CASE
                WHEN s.opcao_pelo_mei = 'S' AND s.data_exclusao_mei = '00000000' THEN 'MEI'
                WHEN COALESCE(emp.porte_empresa, '') IN ('01', '03') THEN 'ME'
                ELSE 'LTDA'
            END AS tipo_empresa
        FROM estabelecimentos est
        LEFT JOIN empresas emp ON est.cnpj_basico = emp.cnpj_basico
        LEFT JOIN (
            SELECT DISTINCT ON (cnpj_basico) cnpj_basico, opcao_pelo_mei, data_exclusao_mei
            FROM simples
            ORDER BY cnpj_basico, opcao_pelo_mei DESC
        ) s ON est.cnpj_basico = s.cnpj_basico
        WHERE est.uf IN ('AL', 'BA', 'CE', 'MA', 'PB', 'PE', 'PI', 'RN', 'SE')
          AND est.situacao_cadastral = '02'
          AND est.data_inicio_atividade >= '{ANO_INICIO}0101'
          AND est.telefone IS NOT NULL
          AND est.telefone != ''
        """)

        try:
            start_time = time.time()
            total_mei = 0
            for df_chunk in pd.read_sql(query, self.engine, chunksize=self.batch_size):
                mei_count = self._process_chunk(df_chunk)
                total_mei += mei_count

            duration = time.time() - start_time
            metrics.record_export_query('nordeste_export', duration)
            logger.info(f"Exportacao concluida! Total MEI exportado: {total_mei}")
        except Exception as e:
            logger.error(f"Erro na exportacao: {e}", exc_info=True)

    def _process_chunk(self, df):
        """Processa chunk e gera todas as segmentacoes. Retorna contagem de MEI."""
        if df.empty:
            return 0

        # Parse de data — suporta YYYYMMDD e YYYY-MM-DD
        dt_series = pd.to_datetime(df['data_inicio_atividade'], format='%Y%m%d', errors='coerce')
        mask_nat = dt_series.isna()
        if mask_nat.any():
            dt_series[mask_nat] = pd.to_datetime(
                df.loc[mask_nat, 'data_inicio_atividade'], errors='coerce'
            )

        df = df.copy()
        df['ano'] = dt_series.dt.year.fillna(0).astype(int)
        df['mes'] = dt_series.dt.month.fillna(0).astype(int)
        df['trimestre'] = dt_series.dt.quarter.fillna(0).astype(int)

        df = df[(df['ano'] >= ANO_INICIO) & (df['ano'] <= ANO_FIM)].copy()
        if df.empty:
            return 0

        df['tipo_empresa'] = df['tipo_empresa'].fillna('LTDA').replace('', 'LTDA')
        df['operadora'] = df['operadora'].fillna('DESCONHECIDO').replace('', 'DESCONHECIDO')

        # Diagnostico MEI por ano
        mei_mask = df['tipo_empresa'] == 'MEI'
        mei_por_ano = df[mei_mask].groupby('ano').size()
        if not mei_por_ano.empty:
            logger.info(f"MEI no chunk por ano: {mei_por_ano.to_dict()}")
        else:
            logger.warning("Nenhum MEI encontrado neste chunk")

        self._export_anual(df)
        self._export_trimestral(df)
        self._export_mensal(df)

        return int(mei_mask.sum())

    def _export_anual(self, df):
        grouped = df.groupby(['uf', 'tipo_empresa', 'ano', 'operadora'])
        for (uf, tipo, ano, op), subset in grouped:
            folder = self.export_paths['anual'] / uf
            folder.mkdir(exist_ok=True)
            self._write_csv(folder / f"{uf} - {tipo} {ano} - {op}.csv", subset)

    def _export_trimestral(self, df):
        grouped = df.groupby(['uf', 'trimestre', 'ano', 'tipo_empresa', 'operadora'])
        for (uf, tri, ano, tipo, op), subset in grouped:
            folder = self.export_paths['trimestral'] / uf
            folder.mkdir(exist_ok=True)
            self._write_csv(folder / f"{uf} - T{tri} {ano} {tipo} - {op}.csv", subset)

    def _export_mensal(self, df):
        grouped = df.groupby(['uf', 'tipo_empresa', 'ano', 'mes', 'operadora'])
        for (uf, tipo, ano, mes, op), subset in grouped:
            folder = self.export_paths['mensal'] / uf
            folder.mkdir(exist_ok=True)
            self._write_csv(folder / f"{uf} - {tipo} {ano}-{mes:02d} - {op}.csv", subset, include_mes=True)

    def _write_csv(self, filepath, subset, include_mes=False):
        cols = ['cnpj_completo', 'razao_social', 'endereco_completo', 'email', 'ano']
        if include_mes:
            cols.append('mes')
        cols += ['telefone', 'operadora', 'tipo_empresa']

        write_header = not filepath.exists()
        subset[cols].to_csv(
            filepath,
            index=False,
            sep='|',
            encoding='utf-8-sig',
            mode='a',
            header=write_header
        )


# Instancia global
exporter_optimized = NordesteExporterOptimized()
