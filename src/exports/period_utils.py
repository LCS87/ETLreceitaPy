"""Regras compartilhadas para classificacao de periodos de exportacao."""

from datetime import date

ANO_DETALHE_MINIMO = 2020


def _to_int_ano(ano) -> int | None:
    if ano is None:
        return None
    texto = str(ano).strip()
    return int(texto) if texto.isdigit() else None


def ano_em_detalhe(ano) -> bool:
    ano_int = _to_int_ano(ano)
    return ano_int is not None and ANO_DETALHE_MINIMO <= ano_int <= date.today().year


def nome_decada(ano) -> str | None:
    ano_int = _to_int_ano(ano)
    if ano_int is None:
        return None
    return f"decada_{(ano_int // 10) * 10}"
