"""Interface Flask para consulta, preview e exportacao dos dados."""

import hashlib
import io
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from cachetools import TTLCache
from flask import Flask, Response, jsonify, request, render_template_string
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.sql.elements import TextClause

from src.utils.env_loader import config
from src.utils.log_handler import logger

app = Flask(__name__)
_ENGINE = None
PREVIEW_LIMIT = 100

# Cache de contagem: evita re-executar COUNT(*) para os mesmos filtros
# TTL de 5 minutos, máximo de 256 combinações distintas de filtro
_count_cache: TTLCache = TTLCache(maxsize=256, ttl=300)

COLUMN_DEFS = {
    "cnpj_completo": ("e.cnpj_basico || e.cnpj_ordem || e.cnpj_dv", set()),
    "nome_fantasia": ("e.nome_fantasia", set()),
    "situacao_cadastral": ("e.situacao_cadastral", set()),
    "logradouro": ("e.logradouro", set()),
    "numero": ("e.numero", set()),
    "complemento": ("e.complemento", set()),
    "bairro": ("e.bairro", set()),
    "cep": ("e.cep", set()),
    "uf": ("e.uf", set()),
    "ddd_1": ("e.ddd_1", set()),
    "telefone_1": ("e.telefone_1", set()),
    "email": ("e.correio_eletronico", set()),
    "data_inicio_atividade": ("e.data_inicio_atividade", set()),
    "cnae_fiscal_principal": ("e.cnae_fiscal_principal", set()),
    "operadora": ("COALESCE(e.operadora, 'DESCONHECIDO')", set()),
    "categoria": ("e.categoria", set()),
    "razao_social": ("emp.razao_social", {"empresas"}),
    "natureza_juridica": ("emp.natureza_juridica", {"empresas"}),
    "porte_empresa": ("emp.porte_empresa", {"empresas"}),
    "capital_social": ("emp.capital_social", {"empresas"}),
    "opcao_simples": ("s.opcao_pelo_simples", {"simples"}),
    "opcao_mei": ("COALESCE(s.opcao_pelo_mei, 'N')", {"simples"}),
    "cidade": ("m.descricao", {"municipios"}),
}

COLUMN_GROUPS = {
    "estabelecimento": [name for name in COLUMN_DEFS if name in {"cnpj_completo", "nome_fantasia", "situacao_cadastral", "logradouro", "numero", "complemento", "bairro", "cep", "uf", "ddd_1", "telefone_1", "email", "data_inicio_atividade", "cnae_fiscal_principal", "operadora", "categoria"}],
    "empresa": [name for name in COLUMN_DEFS if name in {"razao_social", "natureza_juridica", "porte_empresa", "capital_social"}],
    "simples": ["opcao_simples", "opcao_mei"],
    "localizacao": ["cidade", "bairro", "uf", "cep"],
}


def get_engine() -> Engine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = create_engine(
            config.DATABASE_URL,
            pool_pre_ping=True,
            # Usa pool da config em vez de valores fixos
            pool_size=getattr(config, 'POSTGRES_POOL_SIZE', 10),
            max_overflow=getattr(config, 'POSTGRES_MAX_OVERFLOW', 20),
        )
    return _ENGINE


def _make_filter_key(columns: list, filters: dict) -> str:
    """Gera chave de cache determinística para um conjunto de filtros."""
    payload = json.dumps({"c": sorted(columns), "f": filters}, sort_keys=True)
    return hashlib.md5(payload.encode()).hexdigest()


def build_query(
    columns: List[str],
    filters: Dict[str, Any],
    limit: Optional[int] = None,
    include_total_window: bool = False,
) -> Tuple[TextClause, Dict[str, Any]]:
    """
    Constrói a query SQL parametrizada.

    Otimizações aplicadas:
    - UF usa comparação exata (=) para aproveitar idx_establ_uf
    - bairro/cidade usam ILIKE '%...%' — idealmente com pg_trgm no banco
    - include_total_window=True injeta COUNT(*) OVER() para evitar
      segundo round-trip de contagem
    """
    columns = [column for column in columns if column in COLUMN_DEFS]
    if not columns:
        columns = ["cnpj_completo"]
    joins = set()
    select_parts = []
    for column in columns:
        expression, required_joins = COLUMN_DEFS[column]
        select_parts.append(f"{expression} AS {column}")
        joins.update(required_joins)

    # Window function: total sem segunda query
    if include_total_window:
        select_parts.append("COUNT(*) OVER() AS _total_count")

    from_sql = "FROM estabelecimentos e"
    if "empresas" in joins:
        from_sql += " LEFT JOIN empresas emp ON emp.cnpj_basico = e.cnpj_basico"
    if "simples" in joins:
        from_sql += " LEFT JOIN simples s ON s.cnpj_basico = e.cnpj_basico"
    if "municipios" in joins or filters.get("cidade"):
        from_sql += " LEFT JOIN municipios m ON m.codigo = e.municipio"

    clauses = ["e.situacao_cadastral = '02'"]
    params = {}

    # UF: comparação exata (usa índice B-tree idx_establ_uf)
    uf_val = (filters.get("uf") or "").strip().upper()
    if uf_val:
        clauses.append("e.uf = :filter_uf")
        params["filter_uf"] = uf_val

    # Bairro e cidade: ILIKE — usa idx GIN pg_trgm se existir
    for field, expression, value in (
        ("bairro", "e.bairro", filters.get("bairro")),
        ("cidade", "m.descricao", filters.get("cidade")),
    ):
        if value and value.strip():
            key = f"filter_{field}"
            clauses.append(f"{expression} ILIKE :{key}")
            params[key] = f"%{value.strip()}%"

    if filters.get("categoria"):
        clauses.append("e.categoria = :filter_categoria")
        params["filter_categoria"] = filters["categoria"]

    query = f"SELECT {', '.join(select_parts)} {from_sql} WHERE {' AND '.join(clauses)}"
    if limit is not None:
        query += " LIMIT :query_limit"
        params["query_limit"] = max(1, min(int(limit), 1_000_000))
    return text(query), params


@app.get("/")
def index() -> str:
    return render_template_string(HTML_TEMPLATE)


@app.get("/api/columns")
def columns() -> Response:
    return jsonify({"columns": list(COLUMN_DEFS), "groups": COLUMN_GROUPS})


@app.post("/api/preview")
def preview() -> Any:
    try:
        data = request.get_json(silent=True) or {}
        filters = data.get("filters") or {}
        req_cols = data.get("columns") or list(COLUMN_DEFS)

        # --- Contagem com cache TTL de 5 min ---
        cache_key = _make_filter_key(req_cols, filters)
        if cache_key in _count_cache:
            total = _count_cache[cache_key]
            # Busca só os dados (sem window, já temos o total)
            query, params = build_query(req_cols, filters, PREVIEW_LIMIT, include_total_window=False)
            dataframe = pd.read_sql(query, get_engine(), params=params).fillna("").astype(str)
        else:
            # Single query: dados + COUNT(*) OVER() — uma só viagem ao banco
            query, params = build_query(req_cols, filters, PREVIEW_LIMIT, include_total_window=True)
            dataframe = pd.read_sql(query, get_engine(), params=params).fillna("").astype(str)
            if "_total_count" in dataframe.columns:
                total = int(dataframe["_total_count"].iloc[0]) if len(dataframe) else 0
                dataframe = dataframe.drop(columns=["_total_count"])
            else:
                total = len(dataframe)
            _count_cache[cache_key] = total

        return jsonify({
            "columns": list(dataframe.columns),
            "rows": dataframe.values.tolist(),
            "records_count": total,
        })
    except Exception as exc:
        logger.error("[WebInterface] erro no preview", exc_info=True)
        return jsonify({"error": str(exc)}), 500


@app.post("/api/export")
def export_data() -> Any:
    try:
        data = request.get_json(silent=True) or {}
        filters = data.get("filters") or {}
        query, params = build_query(data.get("columns") or list(COLUMN_DEFS), filters)
        dataframe = pd.read_sql(query, get_engine(), params=params)
        fmt = str(data.get("format") or "csv").lower()
        filename = f"estabelecimentos_{datetime.now():%Y%m%d_%H%M%S}.{fmt}"
        if fmt == "csv":
            payload = dataframe.to_csv(index=False, sep=";", encoding="utf-8-sig").encode("utf-8")
            mimetype = "text/csv; charset=utf-8"
        elif fmt == "xlsx":
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
                dataframe.to_excel(writer, index=False, sheet_name="dados")
            payload = buffer.getvalue()
            mimetype = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            return jsonify({"error": "Formato invalido"}), 400
        return app.response_class(payload, mimetype=mimetype, headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except Exception as exc:
        logger.error("[WebInterface] erro na exportacao", exc_info=True)
        return jsonify({"error": str(exc)}), 500


def run_interface(port: int = 5000) -> None:
    app.run(host="0.0.0.0", port=int(port), debug=False, threaded=True)


HTML_TEMPLATE = """
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ETLreceitaPy — Consulta de Dados</title>
<meta name="description" content="Interface de consulta e exportação dos dados da Receita Federal processados pelo ETLreceitaPy.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  :root {
    --bg:        #F4F4F4;
    --surface:   #FFFFFF;
    --border:    #D9D9D9;
    --text-main: #111111;
    --text-sec:  #666666;
    --radius-lg: 16px;
    --radius-md: 10px;
    --radius-sm: 8px;
    --shadow-sm: 0 1px 3px rgba(0,0,0,.07), 0 1px 2px rgba(0,0,0,.04);
    --shadow-md: 0 4px 16px rgba(0,0,0,.08);
    --transition: 180ms cubic-bezier(.4,0,.2,1);
  }

  body {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    background: var(--bg);
    color: var(--text-main);
    font-size: 14px;
    line-height: 1.5;
    min-height: 100vh;
  }

  /* ── HEADER ──────────────────────────────── */
  .header {
    background: linear-gradient(135deg, #d9d9d9 0%, #8f8f8f 35%, #4a4a4a 70%, #111111 100%);
    padding: 36px 40px 32px;
    position: relative;
    overflow: hidden;
  }
  .header::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse 60% 80% at 80% 50%, rgba(255,255,255,.06) 0%, transparent 70%);
  }
  .header-inner { position: relative; max-width: 1400px; margin: auto; }
  .header h1 { font-size: 28px; font-weight: 700; letter-spacing: -.5px; color: #fff; margin-bottom: 4px; }
  .header p  { font-size: 13px; color: rgba(255,255,255,.6); margin-bottom: 28px; font-weight: 400; }
  .stats-row { display: flex; gap: 12px; flex-wrap: wrap; }
  .stat-card {
    background: rgba(255,255,255,.1);
    border: 1px solid rgba(255,255,255,.15);
    border-radius: var(--radius-md);
    padding: 14px 20px;
    backdrop-filter: blur(8px);
    min-width: 180px;
  }
  .stat-card .label {
    font-size: 11px; font-weight: 500; color: rgba(255,255,255,.55);
    text-transform: uppercase; letter-spacing: .6px; margin-bottom: 6px;
  }
  .stat-card .value { font-size: 22px; font-weight: 700; color: #fff; letter-spacing: -.4px; }
  .stat-card .value.dim { color: rgba(255,255,255,.35); font-size: 14px; font-weight: 400; }

  /* ── LAYOUT ──────────────────────────────── */
  .layout {
    max-width: 1400px;
    margin: 28px auto;
    padding: 0 24px 60px;
    display: grid;
    grid-template-columns: 280px 1fr;
    gap: 20px;
    align-items: start;
  }

  /* ── CARDS ───────────────────────────────── */
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); box-shadow: var(--shadow-sm); }
  .card-header {
    padding: 16px 20px 12px;
    border-bottom: 1px solid var(--border);
    display: flex; align-items: center; justify-content: space-between;
  }
  .card-header h2 { font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: .7px; color: var(--text-sec); }
  .card-body { padding: 16px 20px; }

  /* ── SIDEBAR ─────────────────────────────── */
  .sidebar { display: flex; flex-direction: column; gap: 16px; }
  .input-group { display: flex; flex-direction: column; gap: 5px; margin-bottom: 12px; }
  .input-group label { font-size: 11px; font-weight: 600; color: var(--text-sec); text-transform: uppercase; letter-spacing: .5px; }
  .input-group input, .input-group select {
    background: #F7F7F7;
    border: 1px solid transparent;
    border-radius: var(--radius-sm);
    padding: 10px 12px;
    font-family: inherit; font-size: 13px; color: var(--text-main);
    box-shadow: 0 1px 2px rgba(0,0,0,.07);
    transition: border-color var(--transition), box-shadow var(--transition);
    outline: none; width: 100%;
  }
  .input-group input::placeholder { color: #AAAAAA; }
  .input-group input:focus, .input-group select:focus {
    border-color: #111; background: #fff;
    box-shadow: 0 0 0 3px rgba(17,17,17,.06);
  }

  /* ── BUTTONS ─────────────────────────────── */
  .btn-group { display: flex; flex-direction: column; gap: 8px; }
  .btn {
    display: flex; align-items: center; justify-content: center; gap: 8px;
    padding: 11px 16px; border: none; border-radius: var(--radius-sm);
    font-family: inherit; font-size: 13px; font-weight: 600;
    cursor: pointer; width: 100%; letter-spacing: .1px;
    transition: transform var(--transition), box-shadow var(--transition), opacity var(--transition);
    position: relative; overflow: hidden;
  }
  .btn::after {
    content: '';
    position: absolute; inset: 0;
    background: rgba(255,255,255,0);
    transition: background var(--transition);
  }
  .btn:hover::after  { background: rgba(255,255,255,.08); }
  .btn:hover  { transform: translateY(-1px); box-shadow: var(--shadow-md); }
  .btn:active { transform: translateY(0); box-shadow: none; }
  .btn:disabled { opacity: .38; cursor: not-allowed; transform: none; box-shadow: none; }
  .btn-primary { background: #111; color: #fff; }
  .btn-csv     { background: #3a3a3a; color: #fff; }
  .btn-xlsx    { background: linear-gradient(135deg, #c8c8c8, #686868, #111); color: #fff; }

  /* Export unlock animation */
  .btn-csv, .btn-xlsx {
    max-height: 0; padding-top: 0; padding-bottom: 0;
    opacity: 0; overflow: hidden;
    transition: max-height .35s ease, padding .35s ease, opacity .25s ease, transform var(--transition), box-shadow var(--transition);
  }
  .btn-csv.unlocked, .btn-xlsx.unlocked {
    max-height: 48px; padding-top: 11px; padding-bottom: 11px; opacity: 1;
  }

  /* ── COLUMN CHIPS ────────────────────────── */
  .chip-section { margin-bottom: 16px; }
  .chip-section:last-child { margin-bottom: 0; }
  .chip-section-label {
    font-size: 10px; font-weight: 700; text-transform: uppercase;
    letter-spacing: .8px; color: var(--text-sec);
    margin-bottom: 8px; display: block;
  }
  .chip-grid { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 12px 6px 10px;
    border-radius: 999px;
    border: 1px solid #E2E2E2;
    background: #FAFAFA;
    font-size: 12px; font-weight: 500; color: #555;
    cursor: pointer; user-select: none;
    transition: background var(--transition), border-color var(--transition),
                color var(--transition), box-shadow var(--transition), transform var(--transition);
  }
  .chip:hover {
    border-color: #BBB; color: #222; background: #F0F0F0;
    transform: translateY(-1px);
  }
  .chip.active {
    background: #111;
    border-color: #111;
    color: #fff;
    box-shadow: 0 2px 8px rgba(0,0,0,.18);
  }
  .chip.active:hover { background: #2a2a2a; border-color: #2a2a2a; }
  .chip .chip-check {
    width: 14px; height: 14px;
    border-radius: 50%;
    border: 1.5px solid currentColor;
    display: inline-flex; align-items: center; justify-content: center;
    flex-shrink: 0; opacity: .45;
    transition: opacity var(--transition), background var(--transition);
  }
  .chip.active .chip-check {
    opacity: 1;
    background: rgba(255,255,255,.18);
    border-color: transparent;
  }
  .chip .chip-check svg { width: 9px; height: 9px; display: none; }
  .chip.active .chip-check svg { display: block; }

  /* Segmented control — Todas / Nenhuma */
  .seg-control {
    display: inline-flex;
    background: #F0F0F0;
    border-radius: 8px;
    padding: 3px;
    gap: 2px;
  }
  .seg-btn {
    border: none; background: transparent;
    font-family: inherit; font-size: 11px; font-weight: 600;
    color: #666; padding: 5px 12px; border-radius: 6px;
    cursor: pointer; letter-spacing: .2px;
    transition: background var(--transition), color var(--transition), box-shadow var(--transition);
  }
  .seg-btn:hover { color: #111; }
  .seg-btn.active {
    background: #fff; color: #111;
    box-shadow: 0 1px 3px rgba(0,0,0,.12);
  }

  /* ── STATUS BAR ──────────────────────────── */
  .status-bar {
    display: none; align-items: center; justify-content: space-between;
    padding: 12px 20px;
    background: var(--surface); border: 1px solid var(--border);
    border-radius: var(--radius-md); box-shadow: var(--shadow-sm);
    margin-bottom: 12px;
  }
  .status-bar.visible { display: flex; }
  .status-count { font-size: 13px; font-weight: 600; }
  .status-error { color: #c0392b; font-size: 13px; }
  .badge {
    font-size: 11px; font-weight: 600;
    background: #111; color: #fff;
    padding: 2px 8px; border-radius: 20px;
  }

  /* ── TABLE ───────────────────────────────── */
  .table-wrap {
    overflow-x: auto;
    border-radius: var(--radius-lg);
    border: 1px solid var(--border);
    background: var(--surface);
    box-shadow: var(--shadow-sm);
  }
  table { border-collapse: collapse; width: 100%; min-width: 600px; font-size: 13px; }
  thead tr { background: #F7F7F7; border-bottom: 2px solid var(--border); }
  thead th {
    padding: 11px 14px; text-align: left;
    font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .6px;
    color: var(--text-sec); white-space: nowrap;
  }
  tbody tr { border-bottom: 1px solid #F0F0F0; transition: background var(--transition); }
  tbody tr:nth-child(even) { background: #FAFAFA; }
  tbody tr:hover { background: #EEEEEE; }
  tbody td {
    padding: 10px 14px; color: var(--text-main);
    white-space: nowrap; max-width: 220px;
    overflow: hidden; text-overflow: ellipsis;
  }
  .empty-state {
    padding: 56px 20px; text-align: center; color: var(--text-sec);
  }
  .empty-state svg { margin-bottom: 12px; opacity: .25; display: block; margin-left: auto; margin-right: auto; }
  .empty-state p { font-size: 14px; font-weight: 500; margin-bottom: 4px; }
  .empty-state small { font-size: 12px; }

  /* ── SPINNER ─────────────────────────────── */
  @keyframes spin { to { transform: rotate(360deg); } }
  .spinner {
    display: inline-block; width: 13px; height: 13px;
    border: 2px solid rgba(255,255,255,.3); border-top-color: #fff;
    border-radius: 50%; animation: spin .6s linear infinite;
  }

  /* ── RESPONSIVE ──────────────────────────── */
  @media (max-width: 960px) {
    .layout { grid-template-columns: 1fr; }
    .header { padding: 24px 20px; }
    .layout { padding: 0 12px 40px; }
  }
</style>
</head>
<body>

<header class="header">
  <div class="header-inner">
    <h1>ETLreceitaPy</h1>
    <p>Consulta e exportação de dados empresariais da Receita Federal</p>
    <div class="stats-row">
      <div class="stat-card"><div class="label">Registros filtrados</div><div class="value dim" id="stat-count">—</div></div>
      <div class="stat-card"><div class="label">Colunas selecionadas</div><div class="value" id="stat-cols">—</div></div>
      <div class="stat-card"><div class="label">Tempo de consulta</div><div class="value dim" id="stat-time">—</div></div>
    </div>
  </div>
</header>

<div class="layout">

  <aside class="sidebar">

    <div class="card">
      <div class="card-header"><h2>Filtros</h2></div>
      <div class="card-body">
        <div class="input-group">
          <label for="uf">UF <span style="color:#aaa;font-weight:400;text-transform:none">(exato)</span></label>
          <input id="uf" placeholder="AL, SP, RJ..." maxlength="2" style="text-transform:uppercase">
        </div>
        <div class="input-group">
          <label for="cidade">Cidade</label>
          <input id="cidade" placeholder="Ex: Maceió, Recife...">
        </div>
        <div class="input-group">
          <label for="bairro">Bairro</label>
          <input id="bairro" placeholder="Ex: Centro, Pajuçara...">
        </div>
        <div class="input-group">
          <label for="categoria">Categoria</label>
          <select id="categoria">
            <option value="">Todas</option>
            <option value="LTDA">LTDA / S.A.</option>
            <option value="ME">ME / EPP</option>
            <option value="MEI">MEI</option>
            <option value="DESCONHECIDO">Desconhecido</option>
          </select>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header"><h2>Ações</h2></div>
      <div class="card-body">
        <div class="btn-group">
          <button class="btn btn-primary" id="btn-query" onclick="runPreview()">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
            Consultar
          </button>
          <button class="btn btn-csv" id="btn-csv" onclick="runDownload('csv')" disabled>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/></svg>
            Exportar CSV
          </button>
          <button class="btn btn-xlsx" id="btn-xlsx" onclick="runDownload('xlsx')" disabled>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14,2 14,8 20,8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
            Exportar XLSX
          </button>
        </div>
      </div>
    </div>

  </aside>

  <main>

    <div class="card" style="margin-bottom:16px">
      <div class="card-header">
        <h2>Colunas</h2>
        <div class="seg-control" role="group" aria-label="Seleção de colunas">
          <button type="button" class="seg-btn active" id="seg-all" onclick="toggleAll(true)">Todas</button>
          <button type="button" class="seg-btn" id="seg-none" onclick="toggleAll(false)">Nenhuma</button>
        </div>
      </div>
      <div class="card-body" id="columns-root">
        <p style="color:var(--text-sec);font-size:13px">Carregando...</p>
      </div>
    </div>

    <div class="status-bar" id="status-bar">
      <div class="status-count" id="status-text"></div>
      <div style="font-size:12px;color:var(--text-sec)" id="status-note"></div>
    </div>

    <div class="table-wrap" id="table-wrap">
      <div class="empty-state">
        <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/></svg>
        <p>Nenhuma consulta realizada</p>
        <small>Configure os filtros e clique em Consultar</small>
      </div>
    </div>

  </main>
</div>

<script>
  /* ── STATE ──────────────────────────── */
  let available = [];
  let activeChips = new Set();

  const groupOrder  = ['estabelecimento','empresa','localizacao','simples'];
  const groupLabels = { estabelecimento:'Estabelecimento', empresa:'Empresa', localizacao:'Localização', simples:'Simples / MEI' };

  /* ── INIT ───────────────────────────── */
  fetch('/api/columns').then(r => r.json()).then(d => {
    available = d.columns;
    activeChips = new Set(available); // todas ativas por padrão
    renderChips(d.groups);
    updateColCount();
  });

  function renderChips(groups) {
    const root = document.getElementById('columns-root');
    const rendered = new Set();
    let html = '';

    for (const g of groupOrder) {
      const cols = (groups[g] || []).filter(c => available.includes(c));
      if (!cols.length) continue;
      html += `<div class="chip-section">
        <span class="chip-section-label">${groupLabels[g] || g}</span>
        <div class="chip-grid">`;
      cols.forEach(c => {
        rendered.add(c);
        html += chipHtml(c);
      });
      html += '</div></div>';
    }

    const rest = available.filter(c => !rendered.has(c));
    if (rest.length) {
      html += `<div class="chip-section">
        <span class="chip-section-label">Outros</span>
        <div class="chip-grid">`;
      rest.forEach(c => { html += chipHtml(c); });
      html += '</div></div>';
    }

    root.innerHTML = html;
    syncSegControl();
  }

  function chipHtml(c) {
    const label = c.replace(/_/g, ' ');
    return `<button type="button" class="chip active" id="chip-${c}" data-col="${c}" onclick="toggleChip('${c}')" aria-pressed="true">
      <span class="chip-check" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3"><polyline points="20 6 9 17 4 12"/></svg></span>${label}
    </button>`;
  }

  function toggleChip(col) {
    const el = document.getElementById('chip-' + col);
    if (activeChips.has(col)) {
      activeChips.delete(col);
      el.classList.remove('active');
      el.setAttribute('aria-pressed', 'false');
    } else {
      activeChips.add(col);
      el.classList.add('active');
      el.setAttribute('aria-pressed', 'true');
    }
    updateColCount();
    syncSegControl();
  }

  function toggleAll(state) {
    available.forEach(c => {
      const el = document.getElementById('chip-' + c);
      if (!el) return;
      if (state) {
        activeChips.add(c);
        el.classList.add('active');
        el.setAttribute('aria-pressed', 'true');
      } else {
        activeChips.delete(c);
        el.classList.remove('active');
        el.setAttribute('aria-pressed', 'false');
      }
    });
    updateColCount();
    syncSegControl();
  }

  function syncSegControl() {
    const all = available.length > 0 && activeChips.size === available.length;
    const none = activeChips.size === 0;
    document.getElementById('seg-all').classList.toggle('active', all);
    document.getElementById('seg-none').classList.toggle('active', none);
  }

  function updateColCount() {
    document.getElementById('stat-cols').textContent = activeChips.size;
    document.getElementById('stat-cols').classList.remove('dim');
  }

  /* ── HELPERS ────────────────────────── */
  function getFilters() {
    return {
      uf:       document.getElementById('uf').value.trim().toUpperCase(),
      cidade:   document.getElementById('cidade').value.trim(),
      bairro:   document.getElementById('bairro').value.trim(),
      categoria:document.getElementById('categoria').value,
    };
  }

  function payload(format) {
    const p = { columns: [...activeChips], filters: getFilters() };
    if (format) p.format = format;
    return p;
  }

  function setLoading(id, loading) {
    const el = document.getElementById(id);
    if (!el) return;
    el.disabled = loading;
    if (loading) { el._orig = el.innerHTML; el.innerHTML = '<span class="spinner"></span> Aguardando...'; }
    else if (el._orig) { el.innerHTML = el._orig; }
  }

  function unlockExports() {
    ['btn-csv','btn-xlsx'].forEach(id => {
      const el = document.getElementById(id);
      el.disabled = false;
      el.classList.add('unlocked');
    });
  }

  /* ── PREVIEW ────────────────────────── */
  async function runPreview() {
    setLoading('btn-query', true);
    const bar  = document.getElementById('status-bar');
    const wrap = document.getElementById('table-wrap');
    try {
      const t0   = Date.now();
      const resp = await fetch('/api/preview', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload()) });
      const data = await resp.json();
      const elapsed = ((Date.now() - t0) / 1000).toFixed(2);

      if (data.error) {
        bar.className = 'status-bar visible';
        document.getElementById('status-text').innerHTML = `<span class="status-error">⚠ ${data.error}</span>`;
        document.getElementById('status-note').textContent = '';
        document.getElementById('stat-count').textContent = 'Erro';
        wrap.innerHTML = `<div class="empty-state"><p style="color:#c0392b">${data.error}</p></div>`;
        return;
      }

      const count = Number(data.records_count).toLocaleString('pt-BR');
      document.getElementById('stat-count').textContent = count;
      document.getElementById('stat-count').classList.remove('dim');
      document.getElementById('stat-time').textContent = `${elapsed}s`;
      document.getElementById('stat-time').classList.remove('dim');

      bar.className = 'status-bar visible';
      document.getElementById('status-text').innerHTML =
        `<strong>${count}</strong> registros encontrados <span class="badge">Preview</span>`;
      document.getElementById('status-note').textContent =
        data.rows && data.rows.length < data.records_count ? `Exibindo ${data.rows.length} de ${count}` : '';

      if (!data.columns || !data.rows.length) {
        wrap.innerHTML = `<div class="empty-state"><p>Nenhum registro encontrado</p><small>Ajuste os filtros</small></div>`;
        return;
      }

      const thead = '<thead><tr>' + data.columns.map(c => `<th>${c.replace(/_/g,' ')}</th>`).join('') + '</tr></thead>';
      const tbody = '<tbody>' + data.rows.map(row =>
        '<tr>' + row.map(v => `<td title="${v}">${v || '—'}</td>`).join('') + '</tr>'
      ).join('') + '</tbody>';
      wrap.innerHTML = `<table>${thead}${tbody}</table>`;

      unlockExports();
    } catch(err) {
      bar.className = 'status-bar visible';
      document.getElementById('status-text').innerHTML = `<span class="status-error">⚠ Erro de conexão: ${err.message}</span>`;
    } finally {
      setLoading('btn-query', false);
    }
  }

  /* ── EXPORT ─────────────────────────── */
  async function runDownload(format) {
    const id = format === 'csv' ? 'btn-csv' : 'btn-xlsx';
    setLoading(id, true);
    try {
      const resp = await fetch('/api/export', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload(format)) });
      if (!resp.ok) {
        const err = await resp.json();
        document.getElementById('status-text').innerHTML = `<span class="status-error">⚠ ${err.error}</span>`;
        return;
      }
      const blob = await resp.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = `export_${new Date().toISOString().slice(0,10)}.${format}`;
      a.click();
      URL.revokeObjectURL(a.href);
    } finally {
      setLoading(id, false);
      // Restore unlocked state after spinner resets
      setTimeout(() => document.getElementById(id).classList.add('unlocked'), 10);
    }
  }

  /* ── SHORTCUTS ──────────────────────── */
  ['uf','cidade','bairro'].forEach(id => {
    document.getElementById(id).addEventListener('keydown', e => { if (e.key === 'Enter') runPreview(); });
  });
  document.getElementById('uf').addEventListener('input', e => {
    e.target.value = e.target.value.toUpperCase();
  });
</script>
</body>
</html>
"""
