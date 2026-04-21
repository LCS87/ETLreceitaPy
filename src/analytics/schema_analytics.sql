-- Schema Analytics para Dashboard de Vendas
-- Autor: Sistema ETL Receita
-- Data: 2026-04-20

-- Criar schema separado para analytics
CREATE SCHEMA IF NOT EXISTS analytics;

-- ============================================
-- TABELAS DIMENSIONAIS
-- ============================================

-- Dimensão Tempo (Mensal)
CREATE TABLE IF NOT EXISTS analytics.dim_tempo (
    id_tempo SERIAL PRIMARY KEY,
    ano INT NOT NULL,
    mes INT NOT NULL,
    trimestre INT NOT NULL,
    ano_mes VARCHAR(7) NOT NULL UNIQUE,  -- formato: 2026-04
    nome_mes VARCHAR(20) NOT NULL,
    dias_uteis INT DEFAULT 22,
    CONSTRAINT chk_mes CHECK (mes BETWEEN 1 AND 12)
);

-- Dimensão Localização (Estados + DDDs)
CREATE TABLE IF NOT EXISTS analytics.dim_localizacao (
    id_localizacao SERIAL PRIMARY KEY,
    uf CHAR(2) NOT NULL,
    nome_estado VARCHAR(50) NOT NULL,
    regiao VARCHAR(20) NOT NULL,
    ddd_principal INT,
    codigo_ibge INT,
    latitude DECIMAL(10,8),
    longitude DECIMAL(11,8),
    CONSTRAINT uk_uf UNIQUE (uf)
);

-- Dimensão Tipo Empresa
CREATE TABLE IF NOT EXISTS analytics.dim_tipo_empresa (
    id_tipo_empresa SERIAL PRIMARY KEY,
    codigo_natureza VARCHAR(10) NOT NULL,
    descricao_natureza VARCHAR(100) NOT NULL,
    categoria VARCHAR(20) NOT NULL,  -- LTDA, MEI, ME, EIRELI, SA, etc
    porte VARCHAR(10),  -- ME, EPP, DEMAIS
    CONSTRAINT uk_codigo_natureza UNIQUE (codigo_natureza)
);

-- ============================================
-- TABELA FATO - MÉTRICAS PRINCIPAIS
-- ============================================

CREATE TABLE IF NOT EXISTS analytics.fato_empresas (
    id_fato BIGSERIAL PRIMARY KEY,
    id_tempo INT NOT NULL REFERENCES analytics.dim_tempo(id_tempo),
    id_localizacao INT NOT NULL REFERENCES analytics.dim_localizacao(id_localizacao),
    id_tipo_empresa INT NOT NULL REFERENCES analytics.dim_tipo_empresa(id_tipo_empresa),
    
    -- Métricas de quantidade
    qtd_empresas_ativas INT DEFAULT 0,
    qtd_empresas_novas INT DEFAULT 0,  -- novas no mês
    qtd_empresas_baixadas INT DEFAULT 0,  -- baixadas no mês
    
    -- Métricas de potencial comercial (Banda Larga / Telefonia)
    qtd_empresas_tecnologia INT DEFAULT 0,  -- empresas de tecnologia/telecom
    qtd_empresas_servicos INT DEFAULT 0,  -- empresas de serviços
    qtd_empresas_comercio INT DEFAULT 0,  -- empresas de comércio
    
    -- Score de potencial (0-100)
    score_potencial_banda_larga DECIMAL(5,2) DEFAULT 0,
    score_potencial_telefonia DECIMAL(5,2) DEFAULT 0,
    
    -- Dados demográficos úteis
    total_funcionarios_estimado INT DEFAULT 0,
    media_funcionarios_por_empresa DECIMAL(6,2) DEFAULT 0,
    
    -- Flags de processamento
    data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    fonte_dados VARCHAR(50) DEFAULT 'RFB',
    
    CONSTRAINT uk_fato UNIQUE (id_tempo, id_localizacao, id_tipo_empresa)
);

-- ============================================
-- TABELA FATO - EVOLUÇÃO MENSAL DETALHADA
-- ============================================

CREATE TABLE IF NOT EXISTS analytics.fato_evolucao_mensal (
    id_evolucao BIGSERIAL PRIMARY KEY,
    id_tempo INT NOT NULL REFERENCES analytics.dim_tempo(id_tempo),
    id_localizacao INT NOT NULL REFERENCES analytics.dim_localizacao(id_localizacao),
    
    -- Evolução por tipo
    qtd_ltda INT DEFAULT 0,
    qtd_mei INT DEFAULT 0,
    qtd_me INT DEFAULT 0,
    qtd_eireli INT DEFAULT 0,
    qtd_sa INT DEFAULT 0,
    qtd_outros INT DEFAULT 0,
    
    -- Crescimento percentual (vs mês anterior)
    crescimento_ltda DECIMAL(8,4) DEFAULT 0,
    crescimento_mei DECIMAL(8,4) DEFAULT 0,
    crescimento_me DECIMAL(8,4) DEFAULT 0,
    crescimento_total DECIMAL(8,4) DEFAULT 0,
    
    -- Ranking por estado
    rank_por_qtd INT,
    rank_por_crescimento INT,
    
    data_processamento TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT uk_evolucao UNIQUE (id_tempo, id_localizacao)
);

-- ============================================
-- VIEWS PARA DASHBOARD
-- ============================================

-- View: Resumo por Estado
CREATE OR REPLACE VIEW analytics.vw_resumo_estado AS
SELECT 
    l.uf,
    l.nome_estado,
    l.regiao,
    t.ano_mes,
    SUM(f.qtd_empresas_ativas) as total_empresas,
    SUM(f.qtd_empresas_novas) as novas_empresas,
    SUM(CASE WHEN te.categoria = 'MEI' THEN f.qtd_empresas_ativas ELSE 0 END) as total_mei,
    SUM(CASE WHEN te.categoria = 'LTDA' THEN f.qtd_empresas_ativas ELSE 0 END) as total_ltda,
    SUM(CASE WHEN te.categoria = 'ME' THEN f.qtd_empresas_ativas ELSE 0 END) as total_me,
    AVG(f.score_potencial_banda_larga) as score_banda_larga,
    AVG(f.score_potencial_telefonia) as score_telefonia,
    SUM(f.qtd_empresas_tecnologia) as empresas_tecnologia,
    SUM(f.qtd_empresas_servicos) as empresas_servicos,
    SUM(f.total_funcionarios_estimado) as funcionarios_estimados
FROM analytics.fato_empresas f
JOIN analytics.dim_localizacao l ON f.id_localizacao = l.id_localizacao
JOIN analytics.dim_tempo t ON f.id_tempo = t.id_tempo
LEFT JOIN analytics.dim_tipo_empresa te ON f.id_tipo_empresa = te.id_tipo_empresa
GROUP BY l.uf, l.nome_estado, l.regiao, t.ano_mes;

-- View: Evolução Mensal (Linha de Tendência)
CREATE OR REPLACE VIEW analytics.vw_evolucao_mensal AS
SELECT 
    t.ano,
    t.mes,
    t.ano_mes,
    t.nome_mes,
    SUM(f.qtd_empresas_ativas) as total_empresas,
    SUM(f.qtd_empresas_novas) as empresas_novas,
    SUM(CASE WHEN te.categoria = 'MEI' THEN f.qtd_empresas_ativas ELSE 0 END) as total_mei,
    SUM(CASE WHEN te.categoria = 'LTDA' THEN f.qtd_empresas_ativas ELSE 0 END) as total_ltda,
    SUM(CASE WHEN te.categoria = 'ME' THEN f.qtd_empresas_ativas ELSE 0 END) as total_me,
    LAG(SUM(f.qtd_empresas_ativas)) OVER (ORDER BY t.ano, t.mes) as total_mes_anterior,
    CASE 
        WHEN LAG(SUM(f.qtd_empresas_ativas)) OVER (ORDER BY t.ano, t.mes) > 0 
        THEN ((SUM(f.qtd_empresas_ativas) - LAG(SUM(f.qtd_empresas_ativas)) OVER (ORDER BY t.ano, t.mes))::DECIMAL / LAG(SUM(f.qtd_empresas_ativas)) OVER (ORDER BY t.ano, t.mes)) * 100
        ELSE 0 
    END as crescimento_percentual
FROM analytics.fato_empresas f
JOIN analytics.dim_tempo t ON f.id_tempo = t.id_tempo
LEFT JOIN analytics.dim_tipo_empresa te ON f.id_tipo_empresa = te.id_tipo_empresa
GROUP BY t.ano, t.mes, t.ano_mes, t.nome_mes
ORDER BY t.ano, t.mes;

-- View: Mapa de Calor - Tipo Empresa por Estado
CREATE OR REPLACE VIEW analytics.vw_mapa_tipo_estado AS
SELECT 
    l.uf,
    l.nome_estado,
    l.regiao,
    te.categoria,
    SUM(f.qtd_empresas_ativas) as quantidade,
    SUM(f.qtd_empresas_ativas) * 100.0 / NULLIF(SUM(SUM(f.qtd_empresas_ativas)) OVER (PARTITION BY l.uf), 0) as percentual_no_estado
FROM analytics.fato_empresas f
JOIN analytics.dim_localizacao l ON f.id_localizacao = l.id_localizacao
JOIN analytics.dim_tipo_empresa te ON f.id_tipo_empresa = te.id_tipo_empresa
GROUP BY l.uf, l.nome_estado, l.regiao, te.categoria;

-- View: Top Estados (Barras)
CREATE OR REPLACE VIEW analytics.vw_top_estados AS
SELECT 
    l.uf,
    l.nome_estado,
    l.regiao,
    SUM(f.qtd_empresas_ativas) as total_empresas,
    SUM(f.qtd_empresas_novas) as novas_empresas,
    AVG(f.score_potencial_banda_larga) as score_banda_larga,
    AVG(f.score_potencial_telefonia) as score_telefonia,
    ROW_NUMBER() OVER (ORDER BY SUM(f.qtd_empresas_ativas) DESC) as rank_geral
FROM analytics.fato_empresas f
JOIN analytics.dim_localizacao l ON f.id_localizacao = l.id_localizacao
GROUP BY l.uf, l.nome_estado, l.regiao
ORDER BY total_empresas DESC;

-- View: Potencial Comercial por Segmento
CREATE OR REPLACE VIEW analytics.vw_potencial_comercial AS
SELECT 
    l.uf,
    l.nome_estado,
    t.ano_mes,
    SUM(f.qtd_empresas_tecnologia) as empresas_tec,
    SUM(f.qtd_empresas_servicos) as empresas_svc,
    SUM(f.qtd_empresas_comercio) as empresas_com,
    SUM(f.total_funcionarios_estimado) as funcionarios_total,
    AVG(f.score_potencial_banda_larga) as score_banda_larga,
    AVG(f.score_potencial_telefonia) as score_telefonia,
    -- Estimativa de potencial: empresas tecnologia * score banda larga
    (SUM(f.qtd_empresas_tecnologia) * AVG(f.score_potencial_banda_larga) / 100)::INT as potencial_estimado
FROM analytics.fato_empresas f
JOIN analytics.dim_localizacao l ON f.id_localizacao = l.id_localizacao
JOIN analytics.dim_tempo t ON f.id_tempo = t.id_tempo
GROUP BY l.uf, l.nome_estado, t.ano_mes;

-- View: Distribuição por Tipo de Empresa
CREATE OR REPLACE VIEW analytics.vw_distribuicao_tipo AS
SELECT 
    te.categoria,
    SUM(f.qtd_empresas_ativas) as quantidade,
    AVG(f.score_potencial_banda_larga) as avg_score_bl,
    AVG(f.score_potencial_telefonia) as avg_score_tel,
    SUM(f.total_funcionarios_estimado) as funcionarios
FROM analytics.fato_empresas f
JOIN analytics.dim_tipo_empresa te ON f.id_tipo_empresa = te.id_tipo_empresa
GROUP BY te.categoria
ORDER BY quantidade DESC;

-- View: Crescimento por Estado
CREATE OR REPLACE VIEW analytics.vw_crescimento_estado AS
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
    e.crescimento_total,
    e.rank_por_qtd,
    e.rank_por_crescimento
FROM analytics.fato_evolucao_mensal e
JOIN analytics.dim_localizacao l ON e.id_localizacao = l.id_localizacao
JOIN analytics.dim_tempo t ON e.id_tempo = t.id_tempo
ORDER BY l.uf, t.ano_mes;

-- ============================================
-- ÍNDICES PARA PERFORMANCE
-- ============================================

CREATE INDEX IF NOT EXISTS idx_fato_tempo ON analytics.fato_empresas(id_tempo);
CREATE INDEX IF NOT EXISTS idx_fato_localizacao ON analytics.fato_empresas(id_localizacao);
CREATE INDEX IF NOT EXISTS idx_fato_tipo ON analytics.fato_empresas(id_tipo_empresa);
CREATE INDEX IF NOT EXISTS idx_fato_processamento ON analytics.fato_empresas(data_processamento);

CREATE INDEX IF NOT EXISTS idx_evolucao_tempo ON analytics.fato_evolucao_mensal(id_tempo);
CREATE INDEX IF NOT EXISTS idx_evolucao_localizacao ON analytics.fato_evolucao_mensal(id_localizacao);

-- ============================================
-- FUNÇÃO: Popular dimensão tempo
-- ============================================

CREATE OR REPLACE FUNCTION analytics.popular_dim_tempo(ano_inicial INT, ano_final INT)
RETURNS VOID AS $$
DECLARE
    v_ano INT;
    v_mes INT;
    v_trimestre INT;
    v_nome_mes VARCHAR(20);
    v_ano_mes VARCHAR(7);
BEGIN
    FOR v_ano IN ano_inicial..ano_final LOOP
        FOR v_mes IN 1..12 LOOP
            v_trimestre := ((v_mes - 1) / 3) + 1;
            v_ano_mes := v_ano || '-' || LPAD(v_mes::TEXT, 2, '0');
            
            SELECT CASE v_mes
                WHEN 1 THEN 'Janeiro' WHEN 2 THEN 'Fevereiro' WHEN 3 THEN 'Março'
                WHEN 4 THEN 'Abril' WHEN 5 THEN 'Maio' WHEN 6 THEN 'Junho'
                WHEN 7 THEN 'Julho' WHEN 8 THEN 'Agosto' WHEN 9 THEN 'Setembro'
                WHEN 10 THEN 'Outubro' WHEN 11 THEN 'Novembro' WHEN 12 THEN 'Dezembro'
            END INTO v_nome_mes;
            
            INSERT INTO analytics.dim_tempo (ano, mes, trimestre, ano_mes, nome_mes)
            VALUES (v_ano, v_mes, v_trimestre, v_ano_mes, v_nome_mes)
            ON CONFLICT (ano_mes) DO NOTHING;
        END LOOP;
    END LOOP;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- DADOS INICIAIS
-- ============================================

-- Popular dimensão tempo (2024-2027)
SELECT analytics.popular_dim_tempo(2024, 2027);

-- Popular dimensão localização (Estados brasileiros)
INSERT INTO analytics.dim_localizacao (uf, nome_estado, regiao, ddd_principal, codigo_ibge, latitude, longitude)
VALUES 
    ('AC', 'Acre', 'Norte', 68, 12, -8.77, -70.55),
    ('AL', 'Alagoas', 'Nordeste', 82, 27, -9.71, -35.73),
    ('AP', 'Amapá', 'Norte', 96, 16, 1.41, -51.77),
    ('AM', 'Amazonas', 'Norte', 92, 13, -3.07, -61.66),
    ('BA', 'Bahia', 'Nordeste', 71, 29, -12.96, -38.51),
    ('CE', 'Ceará', 'Nordeste', 85, 23, -3.71, -38.54),
    ('DF', 'Distrito Federal', 'Centro-Oeste', 61, 53, -15.83, -47.86),
    ('ES', 'Espírito Santo', 'Sudeste', 27, 32, -19.19, -40.34),
    ('GO', 'Goiás', 'Centro-Oeste', 62, 52, -16.64, -49.31),
    ('MA', 'Maranhão', 'Nordeste', 98, 21, -2.55, -44.30),
    ('MT', 'Mato Grosso', 'Centro-Oeste', 65, 51, -12.64, -55.42),
    ('MS', 'Mato Grosso do Sul', 'Centro-Oeste', 67, 50, -20.51, -54.54),
    ('MG', 'Minas Gerais', 'Sudeste', 31, 31, -18.10, -44.38),
    ('PA', 'Pará', 'Norte', 91, 15, -5.53, -52.29),
    ('PB', 'Paraíba', 'Nordeste', 83, 25, -7.06, -35.55),
    ('PR', 'Paraná', 'Sul', 41, 41, -24.89, -51.55),
    ('PE', 'Pernambuco', 'Nordeste', 81, 26, -8.28, -35.07),
    ('PI', 'Piauí', 'Nordeste', 86, 22, -6.60, -42.28),
    ('RJ', 'Rio de Janeiro', 'Sudeste', 21, 33, -22.84, -43.15),
    ('RN', 'Rio Grande do Norte', 'Nordeste', 84, 24, -5.81, -36.59),
    ('RS', 'Rio Grande do Sul', 'Sul', 51, 43, -30.01, -51.22),
    ('RO', 'Rondônia', 'Norte', 69, 11, -10.83, -63.34),
    ('RR', 'Roraima', 'Norte', 95, 14, 1.99, -61.33),
    ('SC', 'Santa Catarina', 'Sul', 48, 42, -27.33, -49.44),
    ('SP', 'São Paulo', 'Sudeste', 11, 35, -23.55, -46.64),
    ('SE', 'Sergipe', 'Nordeste', 79, 28, -10.90, -37.07),
    ('TO', 'Tocantins', 'Norte', 63, 17, -10.25, -48.25)
ON CONFLICT (uf) DO NOTHING;

-- Comentários para documentação
COMMENT ON SCHEMA analytics IS 'Schema para analytics e dashboard de vendas';
COMMENT ON TABLE analytics.fato_empresas IS 'Tabela fato principal com métricas de empresas';
COMMENT ON TABLE analytics.fato_evolucao_mensal IS 'Evolução mensal detalhada por estado e tipo';
