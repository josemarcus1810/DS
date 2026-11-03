"""
Regras de senha do sistema (usadas pelo app.py e pelos scripts de usuário).

Regras do projeto:
- mínimo de 8 caracteres e pelo menos 1 caractere especial;
- troca periódica a cada dois meses (aqui: 60 dias);
- motivos de troca: "Esqueci minha senha" e "Solicitação do sistema".
"""

from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

# Horário de Brasília (UTC-3, sem horário de verão desde 2019). Usado em tudo o
# que o sistema grava, para que o servidor na nuvem (que usa UTC) mostre a
# mesma hora que o seu computador.
FUSO_BRASIL = timezone(timedelta(hours=-3))


def agora():
    return datetime.now(FUSO_BRASIL).replace(tzinfo=None)


TAMANHO_MINIMO_SENHA = 8
DIAS_VALIDADE_SENHA = 60

MOTIVO_ESQUECI = "Esqueci minha senha"
MOTIVO_SISTEMA = "Solicitação do sistema"


def validar_nova_senha(senha):
    """Retorna None se a senha é válida; senão, a mensagem de erro."""
    if len(senha) < TAMANHO_MINIMO_SENHA:
        return f"A senha deve ter pelo menos {TAMANHO_MINIMO_SENHA} caracteres."

    # Caractere especial = nem letra, nem número, nem espaço.
    if not any(not c.isalnum() and not c.isspace() for c in senha):
        return "A senha deve ter pelo menos um caractere especial (ex.: ! @ # $ %)."

    return None


def gerar_hash(senha):
    # pbkdf2:sha256 funciona em qualquer instalação do Python.
    return generate_password_hash(senha, method="pbkdf2:sha256")


def conferir_senha(senha_hash, senha):
    return check_password_hash(senha_hash, senha)


def dias_desde_troca(senha_alterada_em, referencia=None):
    referencia = referencia or agora()
    return (referencia - senha_alterada_em).days


def senha_expirada(senha_alterada_em, referencia=None):
    return dias_desde_troca(senha_alterada_em, referencia) >= DIAS_VALIDADE_SENHA
