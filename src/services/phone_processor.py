import phonenumbers
import pandas as pd
from phonenumbers import carrier, PhoneNumberFormat
from src.utils.log_handler import logger


class PhoneProcessor:
    def __init__(self):
        # Heurística de Prefixos Anatel (Mobile)
        # Nota: Portabilidade existe, mas para leads de massa,
        # a taxa de acerto por prefixo original é superior a 85%.
        self.mapa_prefixos = {
            'VIVO': ['971', '972', '995', '996', '997', '998', '999'],
            'TIM': ['969', '979', '981', '982', '983', '991'],
            'CLARO': ['968', '973', '974', '975', '976', '992', '993', '994'],
            'OI': ['984', '985', '986', '987', '988']
        }

    def processar(self, ddd, telefone):
        """
        Recebe DDD e Telefone brutos, retorna (Telefone_Formatado, Operadora)
        """
        if not ddd or not telefone:
            return None, "SEM_NUMERO"

        # Limpeza básica (remover espaços ou caracteres estranhos)
        ddd = str(ddd).strip().replace('.0', '')
        telefone = str(telefone).strip().replace('.0', '').replace('-', '')

        try:
            # Tenta validar com a libphonenumber da Google
            # Formato esperado: +5582999998888
            numero_bruto = f"+55{ddd}{telefone}"
            parsed_number = phonenumbers.parse(numero_bruto, "BR")

            if not phonenumbers.is_valid_number(parsed_number):
                return f"({ddd}) {telefone}", "INVALIDO"

            # 1. Normalização (Formato Nacional: (82) 99999-8888)
            tel_formatado = phonenumbers.format_number(
                parsed_number, PhoneNumberFormat.NATIONAL
            )

            # 2. Identificação da Operadora (Heurística Anatel)
            # Pegamos os primeiros 3 dígitos após o DDD (ex: 998)
            prefixo = telefone[0:3] if len(telefone) >= 3 else ""

            operadora_detectada = "OUTRA"
            for op, lista in self.mapa_prefixos.items():
                if prefixo in lista:
                    operadora_detectada = op
                    break

            # Se a heurística falhar, tentamos o metadado da Google (Carrier)
            if operadora_detectada == "OUTRA":
                res = carrier.name_for_number(parsed_number, "pt-br")
                if res:
                    operadora_detectada = res.upper()

            return tel_formatado, operadora_detectada

        except Exception as e:
            return f"({ddd}) {telefone}", "ERRO_PROCESSAMENTO"

    def aplicar_ao_dataframe(self, df):
        """
        Função de alta performance para aplicar a lógica em massa no DataFrame (Pandas)
        """
        logger.info(f" Normalizando e identificando operadoras para {len(df)} registos...")

        # O Pandas 'apply' com lambda permite processar linha a linha
        # Criamos duas novas colunas: 'telefone' (limpo) e 'operadora'
        # Dentro de aplicar_ao_dataframe no arquivo phone_processor.py
        df[['telefone', 'operadora']] = df.apply(
            lambda row: pd.Series(self.processar(row.get('ddd_1'), row.get('telefone_1'))),
            axis=1
        )

        return df


# Instância única para ser usada no motor de transformação
phone_processor = PhoneProcessor()