
import os
import json
import urllib.request
import urllib.error

from dotenv import load_dotenv

load_dotenv()


def enviar_email(destinatario, assunto, mensagem):
    api_key = os.getenv("BREVO_API_KEY")
    remetente = os.getenv("EMAIL_REMETENTE")

    if not api_key:
        raise RuntimeError(
            "A variável BREVO_API_KEY não está configurada."
        )

    if not remetente:
        raise RuntimeError(
            "A variável EMAIL_REMETENTE não está configurada."
        )

    dados = {
        "sender": {
            "name": "Sistema de Almoxarifado",
            "email": remetente
        },
        "to": [
            {
                "email": destinatario
            }
        ],
        "subject": assunto,
        "textContent": mensagem
    }

    corpo = json.dumps(dados).encode("utf-8")

    requisicao = urllib.request.Request(
        url="https://api.brevo.com/v3/smtp/email",
        data=corpo,
        headers={
            "accept": "application/json",
            "api-key": api_key,
            "content-type": "application/json"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(
            requisicao,
            timeout=30
        ) as resposta:

            resultado = json.loads(
                resposta.read().decode("utf-8")
            )

            print(
                "E-mail enviado pela Brevo:",
                resultado.get("messageId")
            )

            return True

    except urllib.error.HTTPError as erro:
        detalhes = erro.read().decode(
            "utf-8",
            errors="replace"
        )

        raise RuntimeError(
            f"Erro da API Brevo ({erro.code}): {detalhes}"
        )

    except urllib.error.URLError as erro:
        raise RuntimeError(
            f"Falha de conexão com a API Brevo: {erro.reason}"
        )
