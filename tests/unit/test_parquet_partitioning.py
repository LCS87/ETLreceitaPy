"""
Testes para o particionamento por UF do OptimizedParquetProcessor.

Valida a integração de `_process_zip_with_partitioning` no fluxo principal
(transform → worker): criação de diretórios `uf=XX/`, escrita por grupo e
fallback para arquivo único quando não há coluna UF.
"""
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from src.core.interfaces import SkippableError
from src.transform.optimized_parquet_processor import (
    OptimizedParquetProcessor,
    _process_file_worker,
)

COLUMNS_UF = ['cnpj_basico', 'uf', 'razao_social']
COLUMNS_SEM_UF = ['cnpj_basico', 'razao_social']


def _make_zip(path: Path, rows, columns) -> Path:
    """Cria ZIP com CSV interno separado por ';' sem header (formato Receita)."""
    lines = [';'.join(row) for row in rows]
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('dados.csv', '\n'.join(lines))
    return path


@pytest.fixture
def workdir(tmp_path):
    raw = tmp_path / 'raw'
    silver = tmp_path / 'silver'
    raw.mkdir()
    silver.mkdir()
    return raw, silver


class TestPartitioning:
    """Testes diretos de _process_zip_with_partitioning."""

    def test_creates_uf_directories(self, workdir):
        raw, silver = workdir
        zip_path = _make_zip(
            raw / 'estabelecimentos.zip',
            [
                ['11111111000191', 'PE', 'EMPRESA A LTDA'],
                ['22222222000192', 'BA', 'EMPRESA B LTDA'],
                ['33333333000193', 'PE', 'EMPRESA C'],
            ],
            COLUMNS_UF,
        )
        out = silver / 'estabelecimentos.parquet'

        proc = OptimizedParquetProcessor(raw_path=raw, silver_path=silver, chunk_size=1000)
        proc._process_zip_with_partitioning(zip_path, out, COLUMNS_UF)

        pe_file = silver / 'uf=PE' / 'estabelecimentos.parquet'
        ba_file = silver / 'uf=BA' / 'estabelecimentos.parquet'
        assert pe_file.exists(), 'Deve criar partição uf=PE'
        assert ba_file.exists(), 'Deve criar partição uf=BA'
        assert not out.exists(), 'Não deve escrever arquivo único quando particionado'

        # Leitura por arquivo (mesmo padrão usado pelo dashboard_direct)
        df_pe = pd.read_parquet(pe_file)
        df_ba = pd.read_parquet(ba_file)
        assert len(df_pe) == 2
        assert len(df_ba) == 1
        assert (df_pe['uf'] == 'PE').all()
        assert (df_ba['uf'] == 'BA').all()

    def test_without_uf_column_writes_single_file(self, workdir):
        raw, silver = workdir
        zip_path = _make_zip(
            raw / 'empresas.zip',
            [
                ['11111111000191', 'EMPRESA A LTDA'],
                ['22222222000192', 'EMPRESA B'],
            ],
            COLUMNS_SEM_UF,
        )
        out = silver / 'empresas.parquet'

        proc = OptimizedParquetProcessor(raw_path=raw, silver_path=silver, chunk_size=1000)
        proc._process_zip_with_partitioning(zip_path, out, COLUMNS_SEM_UF)

        assert out.exists(), 'Sem coluna UF deve escrever arquivo único'
        df = pd.read_parquet(out)
        assert len(df) == 2

    def test_missing_zip_raises(self, workdir):
        raw, silver = workdir
        proc = OptimizedParquetProcessor(raw_path=raw, silver_path=silver, chunk_size=1000)
        with pytest.raises(FileNotFoundError):
            proc._process_zip_with_partitioning(
                raw / 'nao_existe.zip', silver / 'out.parquet', COLUMNS_UF
            )

    def test_corrupted_zip_raises_skippable(self, workdir):
        raw, silver = workdir
        bad = raw / 'corrompido.zip'
        bad.write_bytes(b'nao e um zip valido')
        proc = OptimizedParquetProcessor(raw_path=raw, silver_path=silver, chunk_size=1000)
        with pytest.raises(SkippableError):
            proc._process_zip_with_partitioning(bad, silver / 'out.parquet', COLUMNS_UF)


class TestWorkerDispatch:
    """Valida que o worker do ProcessPoolExecutor escolhe o modo correto."""

    def test_worker_uses_partitioning_when_uf_present(self, workdir):
        raw, silver = workdir
        zip_path = _make_zip(
            raw / 'estabelecimentos.zip',
            [
                ['11111111000191', 'PE', 'EMPRESA A'],
                ['22222222000192', 'BA', 'EMPRESA B'],
            ],
            COLUMNS_UF,
        )
        out = silver / 'estabelecimentos.parquet'

        _process_file_worker(str(zip_path), str(out), COLUMNS_UF, 1000)

        assert (silver / 'uf=PE').exists()
        assert (silver / 'uf=BA').exists()

    def test_worker_uses_enrichment_without_uf(self, workdir):
        raw, silver = workdir
        zip_path = _make_zip(
            raw / 'socios.zip',
            [['11111111000191', 'SOCIO A']],
            COLUMNS_SEM_UF,
        )
        out = silver / 'socios.parquet'

        _process_file_worker(str(zip_path), str(out), COLUMNS_SEM_UF, 1000)

        assert out.exists()
        df = pd.read_parquet(out)
        assert len(df) == 1


class TestSkipExistingPartitions:
    """transform() deve pular arquivos cujas partições por UF já existem."""

    def test_transform_skips_when_partitions_exist(self, workdir, monkeypatch):
        from src.transform import optimized_parquet_processor as mod

        raw, silver = workdir
        # Conteúdo do ZIP não importa: o processamento deve ser pulado
        zip_path = raw / 'Estabelecimentos.zip'
        zip_path.write_bytes(b'dummy')

        part_dir = silver / 'uf=PE'
        part_dir.mkdir()
        (part_dir / 'Estabelecimentos.parquet').write_bytes(b'x' * 10)

        def _boom(*args, **kwargs):
            raise AssertionError(
                'ProcessPoolExecutor não deve ser criado para arquivo já particionado'
            )

        monkeypatch.setattr(mod, 'ProcessPoolExecutor', _boom)

        proc = OptimizedParquetProcessor(raw_path=raw, silver_path=silver, chunk_size=1000)
        # Não deve lançar AssertionError (pool não criado) nem reprocessar
        proc.transform([zip_path])

    def test_transform_processes_when_partitions_absent(self, workdir, monkeypatch):
        from src.transform import optimized_parquet_processor as mod

        raw, silver = workdir
        zip_path = _make_zip(
            raw / 'Estabelecimentos.zip',
            [['11111111000191', 'PE', '02', '', '']],
            ['cnpj_basico', 'uf', 'situacao_cadastral', 'ddd_1', 'telefone_1'],
        )

        pool_calls = []

        class _FakePool:
            def __init__(self, *args, **kwargs):
                pool_calls.append(args)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def submit(self, fn, *args):
                class _F:
                    def result(self):
                        return None
                return _F()

        monkeypatch.setattr(mod, 'ProcessPoolExecutor', _FakePool)
        monkeypatch.setattr(mod, 'as_completed', lambda futures: iter(()))

        proc = OptimizedParquetProcessor(raw_path=raw, silver_path=silver, chunk_size=1000)
        proc.transform([zip_path])

        assert pool_calls, 'Deve processar quando não há partições existentes'
