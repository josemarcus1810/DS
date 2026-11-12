
import os
import ssl
import smtplib

from dotenv import load_dotenv
from email.message import EmailMessage

load_dotenv()


def enviar_email(destinatario, assunto, mensagem):
    servidor = os.getenv("SMTP_SERVER")
    porta = int(os.getenv("SMTP_PORT", "587"))
    login = os.getenv("SMTP_LOGIN")
    senha = os.getenv("SMTP_PASSWORD")
    remetente = os.getenv("EMAIL_REMETENTE")

    if not all([servidor, login, senha, remetente]):
        raise RuntimeError("Configurações SMTP incompletas no ambiente.")

    email = EmailMessage()
    email["Subject"] = assunto
    email["From"] = remetente
    email["To"] = destinatario
    email.set_content(mensagem)

    contexto = ssl.create_default_context()

    with smtplib.SMTP(servidor, porta, timeout=20) as smtp:
        smtp.ehlo()
        smtp.starttls(context=contexto)
        smtp.ehlo()
        smtp.login(login, senha)
        smtp.send_message(email)

    return True
