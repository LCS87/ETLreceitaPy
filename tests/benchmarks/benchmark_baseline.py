"""
Script para coletar métricas baseline do pipeline atual.
Executar ANTES de implementar otimizações para comparação.
"""
import time
import json
import psutil
from pathlib import Path
from datetime import datetime
import pandas as pd

from src.utils.phone_processor_vectorized import PhoneProcessorVectorized
from src.utils.env_loader import config


class BaselineBenchmark:
    def __init__(self):
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'environment': {
                'cpu_count': psutil.cpu_count(logical=True),
                'physical_cores': psutil.cpu_count(logical=False),
                'total_ram_gb': psutil.virtual_memory().total / (1024**3),
                'hostname': config.HOSTNAME
            },
            'benchmarks': {}
        }
    
    def benchmark_phone_processing(self, sample_size=10000):
        """Benchmark do processamento de telefonia atual (linha por linha)"""
        print(f"\n📞 Benchmarking Phone Processing ({sample_size} records)...")
        
        # Gera dados de teste
        df = pd.DataFrame({
            'ddd_1': ['11', '21', '81', '85', '71'] * (sample_size // 5),
            'telefone_1': ['987654321', '912345678', '998765432', '991234567', '987651234'] * (sample_size // 5)
        })
        
        # Mede tempo e recursos
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / (1024**2)  # MB
        
        result_df = PhoneProcessorVectorized().process_batch(df.copy())
        
        end_time = time.time()
        end_memory = psutil.Process().memory_info().rss / (1024**2)  # MB
        
        duration = end_time - start_time
        memory_used = end_memory - start_memory
        
        self.results['benchmarks']['phone_processing'] = {
            'sample_size': sample_size,
            'duration_seconds': round(duration, 2),
            'memory_mb': round(memory_used, 2),
            'records_per_second': round(sample_size / duration, 2)
        }
        
        print(f"  ⏱️  Duration: {duration:.2f}s")
        print(f"  💾 Memory: {memory_used:.2f} MB")
        print(f"  🚀 Throughput: {sample_size/duration:.2f} records/s")
        
        return result_df
    
    def benchmark_parquet_conversion(self):
        """Benchmark da conversão CSV→Parquet (se houver arquivos de teste)"""
        print(f"\n📦 Benchmarking Parquet Conversion...")
        
        # Procura por arquivos de teste pequenos
        test_files = list(config.RAW_DIR.glob("*.zip"))[:1]  # Apenas 1 arquivo para teste
        
        if not test_files:
            print("  ⚠️  No test files found, skipping...")
            return
        
        from src.transform.optimized_parquet_processor import OptimizedParquetProcessor
        processor = OptimizedParquetProcessor(raw_path=config.RAW_DIR, silver_path=config.SILVER_DIR)
        
        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / (1024**2)
        
        try:
            processor.transform(test_files)
        except Exception as e:
            print(f"  ❌ Error: {e}")
            return
        
        end_time = time.time()
        end_memory = psutil.Process().memory_info().rss / (1024**2)
        
        duration = end_time - start_time
        memory_used = end_memory - start_memory
        
        self.results['benchmarks']['parquet_conversion'] = {
            'files_processed': len(test_files),
            'duration_seconds': round(duration, 2),
            'memory_mb': round(memory_used, 2)
        }
        
        print(f"  ⏱️  Duration: {duration:.2f}s")
        print(f"  💾 Memory: {memory_used:.2f} MB")
    
    def benchmark_export_query(self):
        """Benchmark das queries de exportação (se banco estiver disponível)"""
        print(f"\n🔍 Benchmarking Export Query...")
        
        try:
            from src.exports.nordeste_leads import exporter
            from sqlalchemy import text
            
            # Query simplificada para teste
            query = """
            SELECT COUNT(*) 
            FROM estabelecimentos 
            WHERE uf IN ('PE', 'BA') 
              AND situacao_cadastral = '02'
            """
            
            start_time = time.time()
            
            with exporter.engine.connect() as conn:
                result = conn.execute(text(query))
                count = result.scalar()
            
            end_time = time.time()
            duration = end_time - start_time
            
            self.results['benchmarks']['export_query'] = {
                'query_type': 'count_leads',
                'duration_seconds': round(duration, 2),
                'result_count': count
            }
            
            print(f"  ⏱️  Duration: {duration:.2f}s")
            print(f"  📊 Result: {count} records")
            
        except Exception as e:
            print(f"  ⚠️  Database not available: {e}")
    
    def save_results(self, output_file='baseline_metrics.json'):
        """Salva resultados em arquivo JSON"""
        output_path = Path('tests/benchmarks') / output_file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\n✅ Baseline metrics saved to: {output_path}")
        return output_path
    
    def print_summary(self):
        """Imprime resumo dos resultados"""
        print("\n" + "="*60)
        print("📊 BASELINE BENCHMARK SUMMARY")
        print("="*60)
        
        for benchmark_name, metrics in self.results['benchmarks'].items():
            print(f"\n{benchmark_name.upper()}:")
            for key, value in metrics.items():
                print(f"  {key}: {value}")
        
        print("\n" + "="*60)


def main():
    """Executa todos os benchmarks baseline"""
    print("🚀 Starting Baseline Benchmark Collection...")
    print("This will measure current performance BEFORE optimizations.\n")
    
    benchmark = BaselineBenchmark()
    
    # Executa benchmarks
    benchmark.benchmark_phone_processing(sample_size=10000)
    benchmark.benchmark_parquet_conversion()
    benchmark.benchmark_export_query()
    
    # Salva e exibe resultados
    benchmark.save_results()
    benchmark.print_summary()
    
    print("\n💡 Next steps:")
    print("  1. Implement optimizations")
    print("  2. Run: python tests/benchmarks/benchmark_optimized.py")
    print("  3. Compare results to validate improvements")


if __name__ == "__main__":
    main()
