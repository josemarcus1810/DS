
import getpass
import re
import seguranca
from conexao import conectar


def main():
    print("=== Criar usuário do Sistema de Almoxarifado ===")
    print()

    usuario = input("Nome de usuário (login): ").strip()

    if not re.fullmatch(r"[A-Za-z0-9._-]{3,50}", usuario):
        print("Usuário inválido. Use de 3 a 50 caracteres.")
        return

    nome = input("Nome completo: ").strip()

    if not nome or len(nome) > 100:
        print("Informe um nome válido.")
        return

    email = input("E-mail do colaborador: ").strip().lower()

    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        print("Informe um endereço de e-mail válido.")
        return

    senha = getpass.getpass("Senha: ")
    erro = seguranca.validar_nova_senha(senha)

    if erro:
        print(erro)
        return

    if senha != getpass.getpass("Confirme a senha: "):
        print("As senhas não conferem.")
        return

    banco = conectar()
    cursor = banco.cursor()

    try:
        cursor.execute(
            "SELECT id FROM usuarios WHERE usuario = %s",
            (usuario,)
        )

        if cursor.fetchone():
            print("Esse usuário já existe.")
            return

        cursor.execute(
            """
            INSERT INTO usuarios
            (usuario, nome, email, senha_hash, senha_alterada_em)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                usuario,
                nome,
                email,
                seguranca.gerar_hash(senha),
                seguranca.agora()
            )
        )

        banco.commit()
        print()
        print(f"Usuário '{usuario}' criado com sucesso!")
        print("E-mail cadastrado:", email)

    except Exception as erro_banco:
        banco.rollback()
        print("Erro ao criar usuário:", erro_banco)

    finally:
        cursor.close()
        banco.close()


if __name__ == "__main__":
    main()
