def definir_categoria(natureza_juridica, capital_social):
    """
    Define se a empresa é MEI, ME ou LTDA com base na Natureza Jurídica
    Naturezas Comuns:
    2135 = Empresário Individual (Geralmente MEI ou ME)
    2062 = Sociedade Empresária Limitada (LTDA)
    """
    natureza = str(natureza_juridica)
    try:
        capital = float(capital_social)
    except:
        capital = 0

    if natureza == '2135':
        # Teto do MEI em 2026 é 81k (ou valor atualizado)
        return 'MEI' if capital <= 81000 else 'ME'
    elif natureza == '2062':
        return 'LTDA'
    else:
        return 'OUTRA'


def filtrar_emails_contabilidade(email):
    """
    Remove e-mails que provavelmente são de escritórios de contabilidade
    para focar o lead diretamente no dono da empresa.
    """
    if not email:
        return None

    blacklist = ['contabil', 'escritorio', 'assessor', 'contato@cont', 'fiscal']
    email_lower = email.lower()

    for termo in blacklist:
        if termo in email_lower:
            return None  # Ignora o e-mail se for de contador

    return email_lower