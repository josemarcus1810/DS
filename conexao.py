
import os
import mysql.connector


def conectar():
    """
    Conecta ao banco de dados MySQL.

    Por padrão, utiliza o banco local.
    Quando as variáveis de ambiente estiverem configuradas,
    conecta automaticamente ao banco online do Aiven.
    """

    opcoes = {
        "host": os.environ.get(
            "DB_HOST",
            "localhost"
        ),

        "port": int(os.environ.get(
            "DB_PORT",
            "3307"
        )),

        "user": os.environ.get(
            "DB_USER",
            "root"
        ),

        "password": os.environ.get(
            "DB_PASSWORD",
            "root"
        ),

        "database": os.environ.get(
            "DB_NAME",
            "almoxarifado"
        ),

        "charset": "utf8mb4",
        "connection_timeout": 10,

        # Conexão segura exigida pelo Aiven
        "ssl_disabled": False,
    }

    # Certificado SSL, caso seja configurado
    certificado = os.environ.get("DB_SSL_CA")

    if certificado:
        opcoes["ssl_ca"] = certificado
        opcoes["ssl_verify_cert"] = True

    try:
        banco = mysql.connector.connect(**opcoes)

        # Define o horário de Brasília
        cursor = banco.cursor()
        cursor.execute("SET time_zone = '-03:00'")
        cursor.close()

        return banco

    except mysql.connector.Error as erro:
        print(f"Erro ao conectar ao banco de dados: {erro}")
        raise
