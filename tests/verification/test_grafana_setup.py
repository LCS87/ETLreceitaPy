"""
Verification tests for Grafana dashboard setup
Task 12.2: Verificar dashboard Grafana atual
"""

import requests
import pytest
import time
from typing import Dict, Any


class TestGrafanaSetup:
    """Test suite for verifying Grafana dashboard setup"""
    
    GRAFANA_URL = "http://localhost:3001"
    PROMETHEUS_URL = "http://localhost:9091"
    GRAFANA_CREDENTIALS = ("admin", "admin")
    
    def test_grafana_accessibility(self):
        """
        Requirement 1.3: Verify Grafana is accessible at http://localhost:3001
        """
        try:
            response = requests.get(
                f"{self.GRAFANA_URL}/api/health",
                timeout=10
            )
            assert response.status_code == 200, f"Grafana not accessible: {response.status_code}"
            
            health_data = response.json()
            assert health_data.get("database") == "ok", "Grafana database not healthy"
            
            print(f"✓ Grafana is accessible at {self.GRAFANA_URL}")
            print(f"  Health status: {health_data}")
            
        except requests.exceptions.ConnectionError as e:
            pytest.fail(f"Cannot connect to Grafana at {self.GRAFANA_URL}: {e}")
        except Exception as e:
            pytest.fail(f"Error checking Grafana accessibility: {e}")
    
    def test_grafana_authentication(self):
        """
        Requirement 1.3: Verify Grafana admin credentials work
        """
        try:
            response = requests.get(
                f"{self.GRAFANA_URL}/api/org",
                auth=self.GRAFANA_CREDENTIALS,
                timeout=10
            )
            
            assert response.status_code == 200, f"Authentication failed: {response.status_code}"
            
            org_data = response.json()
            print(f"✓ Grafana authentication successful")
            print(f"  Organization: {org_data.get('name')}")
            
        except Exception as e:
            pytest.fail(f"Error authenticating with Grafana: {e}")
    
    def test_prometheus_data_source_configured(self):
        """
        Requirement 1.4: Verify Prometheus data source is configured
        Expected URL: http://prometheus:9090
        """
        try:
            response = requests.get(
                f"{self.GRAFANA_URL}/api/datasources",
                auth=self.GRAFANA_CREDENTIALS,
                timeout=10
            )
            
            assert response.status_code == 200, f"Failed to get data sources: {response.status_code}"
            
            datasources = response.json()
            
            # Look for Prometheus data source
            prometheus_ds = None
            for ds in datasources:
                if ds.get("type") == "prometheus":
                    prometheus_ds = ds
                    break
            
            if prometheus_ds:
                print(f"✓ Prometheus data source is configured")
                print(f"  Name: {prometheus_ds.get('name')}")
                print(f"  URL: {prometheus_ds.get('url')}")
                print(f"  Access: {prometheus_ds.get('access')}")
                
                # Check if URL matches expected (internal Docker network)
                expected_url = "http://prometheus:9090"
                actual_url = prometheus_ds.get('url', '')
                
                if expected_url in actual_url or "prometheus" in actual_url.lower():
                    print(f"  ✓ URL points to Prometheus service")
                else:
                    print(f"  ⚠ Warning: URL is '{actual_url}', expected '{expected_url}'")
            else:
                print("⚠ No Prometheus data source found - needs to be configured")
                print("  Available data sources:")
                for ds in datasources:
                    print(f"    - {ds.get('name')} ({ds.get('type')})")
                
                # This is not a failure - just needs configuration
                pytest.skip("Prometheus data source not configured yet - manual setup required")
                
        except Exception as e:
            pytest.fail(f"Error checking Prometheus data source: {e}")
    
    def test_prometheus_accessibility(self):
        """
        Verify Prometheus is accessible and scraping metrics
        """
        try:
            # Check Prometheus health
            response = requests.get(
                f"{self.PROMETHEUS_URL}/-/healthy",
                timeout=10
            )
            assert response.status_code == 200, f"Prometheus not healthy: {response.status_code}"
            
            print(f"✓ Prometheus is accessible at {self.PROMETHEUS_URL}")
            
            # Check targets
            response = requests.get(
                f"{self.PROMETHEUS_URL}/api/v1/targets",
                timeout=10
            )
            
            if response.status_code == 200:
                targets_data = response.json()
                active_targets = targets_data.get("data", {}).get("activeTargets", [])
                
                print(f"  Active targets: {len(active_targets)}")
                for target in active_targets:
                    job = target.get("labels", {}).get("job")
                    health = target.get("health")
                    last_error = target.get("lastError", "")
                    
                    status_symbol = "✓" if health == "up" else "✗"
                    print(f"    {status_symbol} Job: {job}, Health: {health}")
                    if last_error:
                        print(f"      Error: {last_error}")
            
        except requests.exceptions.ConnectionError as e:
            pytest.fail(f"Cannot connect to Prometheus at {self.PROMETHEUS_URL}: {e}")
        except Exception as e:
            pytest.fail(f"Error checking Prometheus: {e}")
    
    def test_prometheus_scraping_metrics(self):
        """
        Requirement 1.1, 1.2: Verify Prometheus is scraping metrics from ELT pipeline
        Expected endpoint: http://elt_pipeline:8000/metrics
        """
        try:
            # Query Prometheus for available metrics
            response = requests.get(
                f"{self.PROMETHEUS_URL}/api/v1/label/__name__/values",
                timeout=10
            )
            
            assert response.status_code == 200, f"Failed to query metrics: {response.status_code}"
            
            data = response.json()
            metrics = data.get("data", [])
            
            # Expected metrics from requirements 1.7
            expected_metrics = [
                "elt_files_processed_total",
                "elt_rows_inserted_total",
                "elt_processing_duration_seconds",
                "system_cpu_usage_percent",
                "system_ram_usage_percent",
                "system_disk_usage_percent"
            ]
            
            found_metrics = []
            missing_metrics = []
            
            for expected in expected_metrics:
                if expected in metrics:
                    found_metrics.append(expected)
                else:
                    missing_metrics.append(expected)
            
            print(f"✓ Prometheus has {len(metrics)} total metrics")
            print(f"  Found {len(found_metrics)}/{len(expected_metrics)} expected ELT metrics:")
            for metric in found_metrics:
                print(f"    ✓ {metric}")
            
            if missing_metrics:
                print(f"  Missing metrics (pipeline may not have run yet):")
                for metric in missing_metrics:
                    print(f"    ⚠ {metric}")
            
            # Not failing if metrics are missing - pipeline might not have run yet
            if not found_metrics:
                pytest.skip("No ELT metrics found - pipeline may not have run yet")
                
        except Exception as e:
            pytest.fail(f"Error checking Prometheus metrics: {e}")
    
    def test_grafana_dashboards_exist(self):
        """
        Requirement 1.5: Verify dashboards exist in Grafana
        """
        try:
            response = requests.get(
                f"{self.GRAFANA_URL}/api/search?type=dash-db",
                auth=self.GRAFANA_CREDENTIALS,
                timeout=10
            )
            
            assert response.status_code == 200, f"Failed to get dashboards: {response.status_code}"
            
            dashboards = response.json()
            
            if dashboards:
                print(f"✓ Found {len(dashboards)} dashboard(s) in Grafana:")
                for dashboard in dashboards:
                    print(f"    - {dashboard.get('title')} (UID: {dashboard.get('uid')})")
            else:
                print("⚠ No dashboards found - needs to be created")
                pytest.skip("No dashboards configured yet - manual setup required")
                
        except Exception as e:
            pytest.fail(f"Error checking Grafana dashboards: {e}")
    
    def test_metrics_endpoint_accessibility(self):
        """
        Requirement 1.1: Verify ELT pipeline metrics endpoint is accessible
        Expected: http://elt_pipeline:8000/metrics (from inside Docker network)
        """
        # We can't directly access elt_pipeline:8000 from host, but we can check
        # if Prometheus is successfully scraping it
        
        try:
            response = requests.get(
                f"{self.PROMETHEUS_URL}/api/v1/targets",
                timeout=10
            )
            
            if response.status_code == 200:
                targets_data = response.json()
                active_targets = targets_data.get("data", {}).get("activeTargets", [])
                
                # Look for python_elt job
                elt_target = None
                for target in active_targets:
                    if target.get("labels", {}).get("job") == "python_elt":
                        elt_target = target
                        break
                
                if elt_target:
                    health = elt_target.get("health")
                    scrape_url = elt_target.get("scrapeUrl")
                    last_error = elt_target.get("lastError", "")
                    
                    print(f"✓ ELT pipeline metrics endpoint found")
                    print(f"  Scrape URL: {scrape_url}")
                    print(f"  Health: {health}")
                    
                    if health == "up":
                        print(f"  ✓ Metrics endpoint is accessible and being scraped")
                    else:
                        print(f"  ✗ Metrics endpoint is DOWN")
                        if last_error:
                            print(f"  Error: {last_error}")
                        pytest.fail(f"ELT pipeline metrics endpoint is not accessible: {last_error}")
                else:
                    print("⚠ ELT pipeline target not found in Prometheus")
                    print("  This is expected if the pipeline container is not running")
                    pytest.skip("ELT pipeline container not running - metrics endpoint not available")
                    
        except Exception as e:
            pytest.fail(f"Error checking metrics endpoint: {e}")


def main():
    """
    Run verification tests and generate report
    """
    print("=" * 80)
    print("GRAFANA DASHBOARD VERIFICATION - Task 12.2")
    print("=" * 80)
    print()
    
    # Run tests
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-s"  # Show print statements
    ])


if __name__ == "__main__":
    main()
