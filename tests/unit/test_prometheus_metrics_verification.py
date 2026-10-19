"""
Test suite for verifying Prometheus metrics collection (Task 12.1)

This test verifies:
- Endpoint http://elt_pipeline:8000/metrics is accessible
- Prometheus is configured to scrape every 5s (prom_config.yml)
- Required metrics are being collected: files_processed, rows_inserted, 
  processing_duration, cpu_usage, ram_usage, disk_usage

Requirements: 1.1, 1.2, 1.7
"""

import pytest
import requests
import yaml
import time
from pathlib import Path
from prometheus_client.parser import text_string_to_metric_families


class TestPrometheusMetricsVerification:
    """Test suite for Prometheus metrics collection verification"""

    @pytest.fixture
    def prom_config_path(self):
        """Path to Prometheus configuration file"""
        return Path("prom_config.yml")

    @pytest.fixture
    def prom_config(self, prom_config_path):
        """Load Prometheus configuration"""
        with open(prom_config_path, 'r') as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def metrics_endpoint_url(self):
        """Metrics endpoint URL - use localhost when testing outside Docker"""
        # When running inside Docker network, use: http://elt_pipeline:8000/metrics
        # When running from host machine, use: http://localhost:8000/metrics
        return "http://localhost:8000/metrics"

    @pytest.fixture
    def required_metrics(self):
        """List of required metrics that must be exposed"""
        return [
            'elt_files_processed_total',
            'elt_rows_inserted_total',
            'elt_processing_duration_seconds',
            'system_cpu_usage_percent',
            'system_ram_usage_percent',
            'system_disk_usage_percent'
        ]

    def test_prom_config_scrape_interval(self, prom_config):
        """
        Verify that Prometheus is configured to scrape every 5 seconds
        
        Validates: Requirements 1.2
        """
        assert 'global' in prom_config, "Prometheus config missing 'global' section"
        assert 'scrape_interval' in prom_config['global'], "Missing scrape_interval configuration"
        
        scrape_interval = prom_config['global']['scrape_interval']
        assert scrape_interval == '5s', f"Expected scrape_interval '5s', got '{scrape_interval}'"

    def test_prom_config_elt_pipeline_target(self, prom_config):
        """
        Verify that Prometheus is configured to scrape elt_pipeline:8000
        
        Validates: Requirements 1.1
        """
        assert 'scrape_configs' in prom_config, "Prometheus config missing 'scrape_configs'"
        
        # Find the python_elt job
        python_elt_job = None
        for job in prom_config['scrape_configs']:
            if job.get('job_name') == 'python_elt':
                python_elt_job = job
                break
        
        assert python_elt_job is not None, "Missing 'python_elt' job in scrape_configs"
        assert 'static_configs' in python_elt_job, "Missing static_configs in python_elt job"
        
        targets = python_elt_job['static_configs'][0]['targets']
        assert 'elt_pipeline:8000' in targets, f"Expected target 'elt_pipeline:8000', got {targets}"

    def test_metrics_endpoint_accessible(self, metrics_endpoint_url):
        """
        Verify that the metrics endpoint is accessible
        
        Note: This test requires the elt_pipeline container to be running.
        If the container is not running, this test will be skipped.
        
        Validates: Requirements 1.1
        """
        try:
            response = requests.get(metrics_endpoint_url, timeout=5)
            assert response.status_code == 200, f"Metrics endpoint returned status {response.status_code}"
            assert 'text/plain' in response.headers.get('Content-Type', ''), \
                "Metrics endpoint should return text/plain content type"
        except requests.exceptions.ConnectionError:
            pytest.skip("Metrics endpoint not accessible - elt_pipeline container may not be running")
        except requests.exceptions.Timeout:
            pytest.fail("Metrics endpoint timed out")

    def test_required_metrics_exposed(self, metrics_endpoint_url, required_metrics):
        """
        Verify that all required metrics are being exposed
        
        Required metrics (after prometheus_client strips _total suffix from Counters):
        - elt_files_processed (Counter, exposed as elt_files_processed)
        - elt_rows_inserted (Counter, exposed as elt_rows_inserted)
        - elt_processing_duration_seconds (Histogram)
        - system_cpu_usage_percent (Gauge)
        - system_ram_usage_percent (Gauge)
        - system_disk_usage_percent (Gauge)
        
        Validates: Requirements 1.7
        """
        try:
            response = requests.get(metrics_endpoint_url, timeout=5)
            assert response.status_code == 200, "Failed to fetch metrics"
            
            # Parse Prometheus metrics format
            metrics_text = response.text
            exposed_metrics = set()
            
            for family in text_string_to_metric_families(metrics_text):
                exposed_metrics.add(family.name)
            
            # Verify all required metrics are present
            # Note: prometheus_client strips _total suffix from Counter names
            missing_metrics = []
            for metric in required_metrics:
                # Check both with and without _total suffix
                if metric not in exposed_metrics and not metric.endswith('_total'):
                    missing_metrics.append(metric)
                elif metric.endswith('_total') and metric not in exposed_metrics:
                    # Try without _total suffix
                    base_name = metric[:-6]  # Remove '_total'
                    if base_name not in exposed_metrics:
                        missing_metrics.append(metric)
            
            assert len(missing_metrics) == 0, \
                f"Missing required metrics: {missing_metrics}. Exposed metrics: {sorted(exposed_metrics)}"
            
        except requests.exceptions.ConnectionError:
            pytest.skip("Metrics endpoint not accessible - elt_pipeline container may not be running")

    def test_metric_types_correct(self, metrics_endpoint_url):
        """
        Verify that metrics have the correct types
        
        Expected types:
        - files_processed: Counter
        - rows_inserted: Counter
        - processing_duration: Histogram
        - cpu_usage: Gauge
        - ram_usage: Gauge
        - disk_usage: Gauge
        
        Validates: Requirements 1.7
        """
        expected_types = {
            'elt_files_processed_total': 'counter',
            'elt_rows_inserted_total': 'counter',
            'elt_processing_duration_seconds': 'histogram',
            'system_cpu_usage_percent': 'gauge',
            'system_ram_usage_percent': 'gauge',
            'system_disk_usage_percent': 'gauge'
        }
        
        try:
            response = requests.get(metrics_endpoint_url, timeout=5)
            assert response.status_code == 200, "Failed to fetch metrics"
            
            metrics_by_name = {}
            for family in text_string_to_metric_families(response.text):
                metrics_by_name[family.name] = family.type
            
            type_mismatches = []
            for metric_name, expected_type in expected_types.items():
                if metric_name in metrics_by_name:
                    actual_type = metrics_by_name[metric_name]
                    if actual_type != expected_type:
                        type_mismatches.append(
                            f"{metric_name}: expected {expected_type}, got {actual_type}"
                        )
            
            assert len(type_mismatches) == 0, \
                f"Metric type mismatches: {type_mismatches}"
            
        except requests.exceptions.ConnectionError:
            pytest.skip("Metrics endpoint not accessible - elt_pipeline container may not be running")

    def test_metrics_have_labels(self, metrics_endpoint_url):
        """
        Verify that metrics have appropriate labels
        
        Expected labels:
        - files_processed: stage, status, host
        - rows_inserted: table_name, host
        - processing_duration: stage, host
        - cpu_usage: host
        - ram_usage: host
        - disk_usage: host, partition
        
        Validates: Requirements 1.7
        """
        try:
            response = requests.get(metrics_endpoint_url, timeout=5)
            assert response.status_code == 200, "Failed to fetch metrics"
            
            # Parse metrics and check for labels
            metrics_text = response.text
            
            # Check for specific label patterns in the raw text
            # This is a simplified check - in production, you'd parse the full metric structure
            label_checks = {
                'elt_files_processed_total': ['stage=', 'status=', 'host='],
                'elt_rows_inserted_total': ['table_name=', 'host='],
                'elt_processing_duration_seconds': ['stage=', 'host='],
                'system_cpu_usage_percent': ['host='],
                'system_ram_usage_percent': ['host='],
                'system_disk_usage_percent': ['host=', 'partition=']
            }
            
            missing_labels = []
            for metric_name, expected_labels in label_checks.items():
                # Find lines containing this metric
                metric_lines = [line for line in metrics_text.split('\n') if metric_name in line and not line.startswith('#')]
                
                if metric_lines:
                    # Check if at least one line has all expected labels
                    has_all_labels = False
                    for line in metric_lines:
                        if all(label in line for label in expected_labels):
                            has_all_labels = True
                            break
                    
                    if not has_all_labels:
                        missing_labels.append(f"{metric_name} missing labels: {expected_labels}")
            
            assert len(missing_labels) == 0, \
                f"Metrics with missing labels: {missing_labels}"
            
        except requests.exceptions.ConnectionError:
            pytest.skip("Metrics endpoint not accessible - elt_pipeline container may not be running")


class TestPrometheusMetricsDocumentation:
    """Documentation and diagnostic tests"""

    def test_print_diagnostic_info(self):
        """
        Print diagnostic information about the Prometheus setup
        
        This is not a validation test, but provides useful information
        for troubleshooting.
        """
        print("\n" + "="*80)
        print("PROMETHEUS METRICS VERIFICATION - DIAGNOSTIC INFORMATION")
        print("="*80)
        
        # Check prom_config.yml
        config_path = Path("prom_config.yml")
        if config_path.exists():
            print(f"\n✓ prom_config.yml found at: {config_path.absolute()}")
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
                print(f"  - Scrape interval: {config.get('global', {}).get('scrape_interval', 'NOT SET')}")
                print(f"  - Jobs configured: {len(config.get('scrape_configs', []))}")
        else:
            print(f"\n✗ prom_config.yml NOT FOUND at: {config_path.absolute()}")
        
        # Check docker-compose.yml
        compose_path = Path("docker-compose.yml")
        if compose_path.exists():
            print(f"\n✓ docker-compose.yml found at: {compose_path.absolute()}")
        else:
            print(f"\n✗ docker-compose.yml NOT FOUND")
        
        # Check if containers are running
        print("\n" + "-"*80)
        print("DOCKER CONTAINER STATUS")
        print("-"*80)
        
        import subprocess
        try:
            result = subprocess.run(
                ['docker', 'ps', '-a', '--filter', 'name=elt_pipeline', '--format', '{{.Names}}\t{{.Status}}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                print(f"elt_pipeline: {result.stdout.strip()}")
            else:
                print("elt_pipeline: NOT FOUND")
        except Exception as e:
            print(f"elt_pipeline: ERROR checking status - {e}")
        
        try:
            result = subprocess.run(
                ['docker', 'ps', '-a', '--filter', 'name=prometheus', '--format', '{{.Names}}\t{{.Status}}'],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                print(f"prometheus: {result.stdout.strip()}")
            else:
                print("prometheus: NOT FOUND")
        except Exception as e:
            print(f"prometheus: ERROR checking status - {e}")
        
        # Try to access metrics endpoint
        print("\n" + "-"*80)
        print("METRICS ENDPOINT ACCESSIBILITY")
        print("-"*80)
        
        endpoints = [
            "http://localhost:8000/metrics",
            "http://elt_pipeline:8000/metrics"
        ]
        
        for endpoint in endpoints:
            try:
                response = requests.get(endpoint, timeout=2)
                print(f"✓ {endpoint} - Status: {response.status_code}")
            except requests.exceptions.ConnectionError:
                print(f"✗ {endpoint} - Connection refused (container may not be running)")
            except requests.exceptions.Timeout:
                print(f"✗ {endpoint} - Timeout")
            except Exception as e:
                print(f"✗ {endpoint} - Error: {e}")
        
        print("\n" + "="*80)
        print("RECOMMENDATIONS")
        print("="*80)
        print("""
To start the monitoring stack:
  1. docker-compose up -d elt_pipeline prometheus grafana
  2. Wait 10-15 seconds for services to start
  3. Run tests again: pytest tests/unit/test_prometheus_metrics_verification.py -v

To check logs:
  - docker logs elt_pipeline_worker
  - docker logs prometheus_service
  - docker logs grafana_service

To verify metrics manually:
  - curl http://localhost:8000/metrics
  - Open http://localhost:9091 (Prometheus UI)
  - Open http://localhost:3001 (Grafana UI, admin/admin)
        """)
        print("="*80 + "\n")


if __name__ == "__main__":
    # Run diagnostic test when executed directly
    test = TestPrometheusMetricsDocumentation()
    test.test_print_diagnostic_info()
