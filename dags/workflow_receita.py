from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator
from datetime import datetime, timedelta
from docker.types import Mount

# Configurações padrão para resiliência
default_args = {
    'owner': 'data_engineering',
    'depends_on_past': False,
    'start_date': datetime(2024, 1, 1),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=15),
}

with DAG(
    'pipeline_receita_cnpj',
    default_args=default_args,
    description='Orquestra o ELT dos Dados Abertos da Receita Federal',
    schedule_interval='@monthly',  # Roda uma vez por mês, conforme atualização da RF
    catchup=False,
    tags=['receita', 'cnpj', 'elt'],
) as dag:

    # Task única que encapsula o Entrypoint dentro do container Docker
    run_elt_process = DockerOperator(
        task_id='execute_elt_pipeline',
        image='elt_receita_app:latest', # Imagem que criamos no Dockerfile
        api_version='auto',
        auto_remove=True,
        command="python src/app_entrypoint.py",
        docker_url="unix://var/run/docker.sock",
        network_mode="bridge",
        # Monta os volumes para persistência de dados fora do container
        mounts=[
            Mount(source='/caminho/no/host/data', target='/app/data', type='bind'),
            Mount(source='/caminho/no/host/docs/logs', target='/app/docs/logs', type='bind')
        ],
        environment={
            'DB_HOST': 'postgres_receita', # Nome do serviço no docker-compose
            'DB_NAME': 'receita_db',
            'PROMETHEUS_PORT': '8000'
        }
    )

    run_elt_process