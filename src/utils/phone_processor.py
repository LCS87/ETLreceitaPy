import phonenumbers
import pandas as pd
import re
from phonenumbers import carrier, PhoneNumberFormat, PhoneNumberType
from src.utils.log_handler import logger

class PhoneProcessor:
    def __init__(self):
        self.operadoras_principais = ["VIVO", "CLARO", "TIM", "OI"]
        
        # Mapeamento para consolidar operadoras (Faxina de nomes antigos)
        self.mapeamento = {
            "TELEMIG_CELULAR": "VIVO",
            "BRASIL_TELECOM_GSM": "OI",
            "TNL_PCS": "OI",
            "OI_MOVEL": "OI",
            "GLOBAL_VILLAGE_TELECOM": "VIVO",
            "CTBC_CELULAR": "ALGAR"
        }

    def limpar_num(self, ddd, tel):
        d = re.sub(r'\D', '', str(ddd).split('.')[0]) if pd.notna(ddd) else ""
        t = re.sub(r'\D', '', str(tel).split('.')[0]) if pd.notna(tel) else ""
        return d, t

    def processar(self, ddd, telefone):
        ddd_c, tel_c = self.limpar_num(ddd, telefone)
        if not ddd_c or not tel_c: return "SEM_NUMERO", "SEM_NUMERO"
        
        raw_num = f"{ddd_c}{tel_c}"
        if len(raw_num) < 10: return f"({ddd_c}) {tel_c}", "INVALIDO_CURTO"

        try:
            parsed = phonenumbers.parse(f"+55{raw_num}", "BR")
            if not phonenumbers.is_valid_number(parsed) and len(raw_num) == 10:
                if tel_c[0] in '789':
                    parsed = phonenumbers.parse(f"+55{ddd_c}9{tel_c}", "BR")

            tel_f = phonenumbers.format_number(parsed, PhoneNumberFormat.NATIONAL)
            n_type = phonenumbers.phonenumberutil.number_type(parsed)
            
            if n_type == PhoneNumberType.FIXED_LINE:
                return tel_f, "FIXO"

            # Nome da operadora original
            c_name = carrier.name_for_number(parsed, "pt-br").upper().replace(" ", "_")
            
            # Aplica o mapeamento (Telemig -> VIVO, etc)
            if c_name in self.mapeamento:
                c_name = self.mapeamento[c_name]

            if c_name:
                for op in self.operadoras_principais:
                    if op in c_name: return tel_f, op
                return tel_f, c_name
            
            return tel_f, "MOVEL_DESCONHECIDO"

        except Exception:
            return f"({ddd_c}) {tel_c}", "ERRO_PARSING"

    def aplicar_ao_dataframe(self, df):
        # Garante que estamos lendo ddd_1 e telefone_1 (nomes do banco)
        res = [self.processar(d, t) for d, t in zip(df['ddd_1'], df['telefone_1'])]
        df['telefones'] = [r[0] for r in res]
        df['operadora'] = [r[1] for r in res]
        return df

phone_processor = PhoneProcessor()