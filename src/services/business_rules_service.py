"""
Business rules com injeção de dependência.
Implementa Pattern dos serviços desacoplados e regras oficiais da Receita.
"""

from typing import Protocol, Optional
import pandas as pd


class BusinessRulesService(Protocol):
    """Interface para regras de negócio."""

    def categorize_empresa(
            self,
            natureza_juridica: str,
            porte_empresa: str,
            opcao_mei: str
    ) -> str:
        """Categoriza empresa como MEI/ME/LTDA/EPP."""
        ...

    def validate_email(self, email: Optional[str]) -> Optional[str]:
        """Valida e filtra emails de contabilidade."""
        ...


class BusinessRulesServiceImpl(BusinessRulesService):
    """Implementação das regras de negócio seguindo lógica oficial."""

    def categorize_empresa(
            self,
            natureza_juridica: str,
            porte_empresa: str,
            opcao_mei: str
    ) -> str:
        """
        Define categoria baseado na lógica técnica:
        1. MEI: Natureza 2135 + Opção MEI 'S'
        2. LTDA: Natureza 2062
        3. ME: Porte '01' (se não for MEI)
        4. EPP: Porte '03'
        """
        # Normalização dos dados
        nat = str(natureza_juridica).strip()
        porte = str(porte_empresa).zfill(2) if porte_empresa else '00'
        mei = str(opcao_mei).upper().strip() if opcao_mei else 'N'

        # REGRA 1: MEI (Empresário Individual + Optante MEI)
        if nat == '2135' and mei == 'S':
            return 'MEI'

        # REGRA 2: LTDA (Sociedade Empresária Limitada)
        if nat == '2062':
            return 'LTDA'

        # REGRA 3: ME (Microempresa por Porte)
        if porte == '01':
            return 'ME'

        # REGRA 4: EPP (Empresa de Pequeno Porte)
        if porte == '03':
            return 'EPP'

        # Outras naturezas específicas que podem ser úteis
        if nat == '2305': return 'EIRELI_EMP'  # Natureza Empresária
        if nat == '2321': return 'ADV_UNIPESSOAL'

        return 'OUTRA'

    def validate_email(self, email: Optional[str]) -> Optional[str]:
        """
        Remove emails que parecem ser de contadores/escritórios.
        """
        if not email or pd.isna(email):
            return None

        email_lower = str(email).lower().strip()

        # Validação básica
        if '@' not in email_lower or '.' not in email_lower:
            return None

        # Blacklist de palavras contábeis para evitar leads frios
        blacklist = [
            'contabil', 'escritorio', 'assessor', 'contato@cont',
            'fiscal', 'guarda-livros', 'contador', 'accounting',
            'bookkeeping', 'consultoria', 'adm'
        ]

        for termo in blacklist:
            if termo in email_lower:
                return None

        return email_lower


# Instância global para compatibilidade com o motor de transformação
business_rules_service = BusinessRulesServiceImpl()