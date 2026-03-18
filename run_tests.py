"""
Script para executar testes do ETLreceitaPy.
Configura ambiente e executa suítes de testes.
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    """Executa um comando e trata o resultado."""
    print(f"\n{'='*60}")
    print(f"🧪 {description}")
    print(f"{'='*60}")
    print(f"Comando: {cmd}")
    print(f"{'='*60}")
    
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    if result.stdout:
        print("STDOUT:")
        print(result.stdout)
    
    if result.stderr:
        print("STDERR:")
        print(result.stderr)
    
    if result.returncode != 0:
        print(f"❌ Falha com código {result.returncode}")
        return False
    else:
        print(f"✅ Sucesso!")
        return True

def main():
    """Função principal de execução dos testes."""
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)
    
    print("🚀 Iniciando suíte de testes do ETLreceitaPy")
    print(f"📁 Diretório do projeto: {project_root}")
    
    # Verificar se dependências estão instaladas
    print("\n📦 Verificando dependências...")
    if not run_command("pip list | grep pytest", "Verificar pytest instalado"):
        print("Instalando dependências de teste...")
        run_command("pip install -r requirements.txt", "Instalar dependências")
    
    # Testes unitários
    print("\n🔬 Executando testes unitários...")
    unit_success = run_command(
        "pytest tests/test_refactored_components.py -v -m 'unit' --cov=src --cov-report=term-missing",
        "Testes Unitários"
    )
    
    # Testes de integração
    print("\n🔗 Executando testes de integração...")
    integration_success = run_command(
        "pytest tests/test_refactored_components.py -v -m 'integration' --cov=src --cov-report=term-missing",
        "Testes de Integração"
    )
    
    # Testes de API (se disponíveis)
    api_test_file = project_root / "tests" / "test_api.py"
    if api_test_file.exists():
        print("\n🌐 Executando testes de API...")
        api_success = run_command(
            "pytest tests/test_api.py -v -m 'api' --cov=src.api --cov-report=term-missing",
            "Testes de API"
        )
    else:
        print("\n⏭️ Pulando testes de API (arquivo não encontrado)")
        api_success = True
    
    # Relatório de cobertura completo
    print("\n📊 Gerando relatório de cobertura completo...")
    coverage_success = run_command(
        "pytest tests/ -v --cov=src --cov-report=html --cov-report=xml",
        "Cobertura Completa"
    )
    
    # Verificar qualidade do código (opcional)
    print("\n🔍 Verificando qualidade do código...")
    if run_command("which flake8", "Verificar flake8"):
        run_command("flake8 src/ --max-line-length=100 --ignore=E203,W503", "Lint com flake8")
    else:
        print("⏭️ flake8 não encontrado, pulando verificação de estilo")
    
    # Resumo final
    print("\n" + "="*60)
    print("📋 RESUMO DOS TESTES")
    print("="*60)
    
    results = {
        "Unitários": unit_success,
        "Integração": integration_success,
        "API": api_success,
        "Cobertura": coverage_success
    }
    
    all_passed = all(results.values())
    
    for test_type, passed in results.items():
        status = "✅ PASSOU" if passed else "❌ FALHOU"
        print(f"{test_type:15} : {status}")
    
    print("="*60)
    
    if all_passed:
        print("🎉 TODOS OS TESTES PASSARAM!")
        print("\n📈 Relatórios gerados:")
        print("   - HTML: htmlcov/index.html")
        print("   - XML: coverage.xml")
        return 0
    else:
        print("❌ ALGUNS TESTES FALHARAM!")
        print("Verifique os logs acima para detalhes.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
