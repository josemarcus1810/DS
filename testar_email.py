
from servico_email import enviar_email

destinatario = input("Digite seu e-mail para receber o teste: ")

try:
    enviar_email(
        destinatario,
        "Teste - Sistema de Almoxarifado",
        """
Olá!

Este é um e-mail de teste do Sistema de Almoxarifado.

A configuração de envio está funcionando!

Atenciosamente,
Sistema de Almoxarifado
"""
    )

    print("E-mail enviado com sucesso!")

except Exception as erro:
    print("Não foi possível enviar o e-mail.")
    print("Verifique as configurações SMTP.")
    print("Detalhe:", erro)
