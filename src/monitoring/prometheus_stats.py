import platform
import time
import threading
import psutil
from prometheus_client import Counter, Histogram, Summary, Gauge, start_http_server

class MetricsCollector:
    def __init__(self, port=8000):
        self.hostname = platform.node()

        # --- MÉTRICAS DE NEGÓCIO (Existentes) ---
        self.files_processed = Counter(
            'elt_files_processed_total',
            'Total de arquivos processados por estágio',
            ['stage', 'status', 'host']
        )
        self.rows_inserted = Counter(
            'elt_rows_inserted_total',
            'Total de linhas inseridas no PostgreSQL',
            ['table_name', 'host']
        )
        self.processing_time = Histogram(
            'elt_processing_duration_seconds',
            'Tempo gasto em segundos por etapa',
            ['stage', 'host']
        )
        self.processing_time_gauge = Gauge(
            'elt_processing_time',
            'Valores instantâneos de processamento',
            ['stage', 'host']
        )

        # --- NOVAS MÉTRICAS DE SISTEMA (CPU, RAM, DISCO) ---
        self.cpu_usage = Gauge(
            'system_cpu_usage_percent',
            'Uso de CPU em porcentagem',
            ['host']
        )
        self.ram_usage = Gauge(
            'system_ram_usage_percent',
            'Uso de Memória RAM em porcentagem',
            ['host']
        )
        self.ram_available = Gauge(
            'system_ram_available_mb',
            'Memória RAM disponível em MB',
            ['host']
        )
        self.disk_usage = Gauge(
            'system_disk_usage_percent',
            'Uso de Disco em porcentagem (Partição Principal)',
            ['host', 'partition']
        )

        # --- MÉTRICAS DE OTIMIZAÇÃO (Task 9.1) ---
        self.phone_processing_duration = Histogram(
            'elt_phone_processing_duration_seconds',
            'Tempo de processamento de telefonia em segundos',
            ['host']
        )
        self.phone_processing_batch_size = Gauge(
            'elt_phone_processing_batch_size',
            'Tamanho do batch de processamento de telefonia',
            ['host']
        )
        self.parquet_enrichment_throughput = Gauge(
            'elt_parquet_enrichment_rows_per_second',
            'Taxa de enriquecimento Parquet em linhas por segundo',
            ['host']
        )
        self.export_query_duration = Histogram(
            'elt_export_query_duration_seconds',
            'Tempo de execução de queries de exportação',
            ['query_type', 'host']
        )
        self.parallel_workers_active = Gauge(
            'elt_parallel_workers_active',
            'Número de workers paralelos ativos',
            ['host']
        )
        self.database_index_usage = Counter(
            'elt_database_index_usage_count',
            'Contador de uso de índices do banco de dados',
            ['index_name', 'host']
        )
        
        # --- MÉTRICA DE VOLUME DE DADOS ---
        self.data_volume = Counter(
            'elt_data_volume_mb',
            'Volume de dados processados em MB',
            ['stage', 'host']
        )

        try:
            start_http_server(port)
            print(f" Servidor de métricas rodando na porta {port} (Host: {self.hostname})")
            self._initialize_metrics()

            # Inicia a thread de monitoramento de hardware
            self._start_hardware_monitor()

        except Exception as e:
            print(f"️ Servidor de métricas já ativo ou erro: {e}")

    def _initialize_metrics(self):
        # Inicializa labels comuns para evitar que venham vazias no Prometheus
        stages = ['download', 'transform', 'postgres', 'export', 'discovery']
        for stage in stages:
            self.processing_time_gauge.labels(stage=stage, host=self.hostname).set(0)

    def _start_hardware_monitor(self):
        """Thread para atualizar CPU/RAM/DISCO corrigida."""

        def monitor():
            while True:
                try:
                    # CORREÇÃO: O nome correto é cpu_percent
                    cpu = psutil.cpu_percent(interval=1)
                    self.cpu_usage.labels(host=self.hostname).set(cpu)

                    ram = psutil.virtual_memory()
                    self.ram_usage.labels(host=self.hostname).set(ram.percent)
                    self.ram_available.labels(host=self.hostname).set(ram.available / (1024 * 1024))

                    # Tenta ler o disco (C: no Windows geralmente é a raiz)
                    try:
                        disk = psutil.disk_usage('C:')
                        self.disk_usage.labels(host=self.hostname, partition='C').set(disk.percent)
                    except:
                        pass

                except Exception as e:
                    print(f"️ Erro ao coletar hardware: {e}")

                time.sleep(10)  # Aumentei para 10s para ser mais leve

        thread = threading.Thread(target=monitor, daemon=True)
        thread.start()

    # --- MÉTODOS DE TRACKING (Mantidos) ---
    def track_duration(self, stage):
        class TimerContext:
            def __init__(self, collector, stage):
                self.collector = collector
                self.stage = stage
                self.start_time = None

            def __enter__(self):
                self.start_time = time.time()
                return self

            def __exit__(self, exc_type, exc_val, exc_tb):
                duration = time.time() - self.start_time
                self.collector.processing_time.labels(stage=self.stage, host=self.collector.hostname).observe(duration)
                self.collector.processing_time_gauge.labels(stage=self.stage, host=self.collector.hostname).set(
                    duration)

        return TimerContext(self, stage)

    def record_file(self, stage, status="success"):
        self.files_processed.labels(stage=stage, status=status, host=self.hostname).inc()

    def record_rows(self, table_name, count):
        self.rows_inserted.labels(table_name=table_name, host=self.hostname).inc(count)

    # --- MÉTODOS DE MÉTRICAS DE OTIMIZAÇÃO (Task 9.1) ---
    def record_phone_batch(self, batch_size, duration):
        """Registra processamento de batch de telefonia"""
        self.phone_processing_batch_size.labels(host=self.hostname).set(batch_size)
        self.phone_processing_duration.labels(host=self.hostname).observe(duration)

    def record_enrichment_throughput(self, rows_per_second):
        """Registra throughput de enriquecimento Parquet"""
        self.parquet_enrichment_throughput.labels(host=self.hostname).set(rows_per_second)

    def record_export_query(self, query_type, duration):
        """Registra duração de query de exportação"""
        self.export_query_duration.labels(query_type=query_type, host=self.hostname).observe(duration)

    def record_parallel_workers(self, worker_count):
        """Registra número de workers paralelos ativos"""
        self.parallel_workers_active.labels(host=self.hostname).set(worker_count)

    def record_index_usage(self, index_name):
        """Registra uso de índice do banco de dados"""
        self.database_index_usage.labels(index_name=index_name, host=self.hostname).inc()

    def record_volume(self, stage, size_mb):
        """Registra volume de dados processados em MB"""
        self.data_volume.labels(stage=stage, host=self.hostname).inc(size_mb)


# Instância global
metrics = MetricsCollector()