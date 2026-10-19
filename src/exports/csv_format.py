"""Contrato comum de escrita dos CSVs de exportacao."""

import csv

import pandas as pd

CSV_SEP = ";"
CSV_ENCODING = "utf-8-sig"
CSV_QUOTING = csv.QUOTE_MINIMAL


def sanitize_text_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Remove quebras de linha e espacos excedentes dos campos textuais."""
    text_cols = df.select_dtypes(include=["object", "string"]).columns
    for coluna in text_cols:
        if hasattr(df[coluna], "str"):
            df[coluna] = (
                df[coluna]
                .fillna("")
                .astype(str)
                .str.replace(r"[\r\n]+", " ", regex=True)
                .str.strip()
            )
    return df
