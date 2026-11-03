import os

import mysql.connector


def conectar():
    """
    Abre uma conexão com o MySQL.

    Os valores padrão abaixo são os do MySQL no seu computador. Para usar
    outro banco (por exemplo, na nuvem), defina as variáveis de ambiente
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD e DB_NAME (e, se o serviço exigir,
    DB_SSL_CA com o caminho do certificado). Não é preciso editar este arquivo.
    """
    opcoes = {
        "host": os.environ.get("DB_HOST", "localhost"),
        "port": int(os.environ.get("DB_PORT", "3307")),
        "user": os.environ.get("DB_USER", "root"),
        "password": os.environ.get("DB_PASSWORD", "root"),
        "database": os.environ.get("DB_NAME", "almoxarifado"),
        "charset": "utf8mb4",
        # Evita o site ficar "travado" se o banco estiver desligado.
        "connection_timeout": 10,
    }

    certificado = os.environ.get("DB_SSL_CA")
    if certificado:
        opcoes["ssl_ca"] = certificado

    banco = mysql.connector.connect(**opcoes)

    # Horário de Brasília nesta conexão (servidores na nuvem usam UTC).
    cursor = banco.cursor()
    cursor.execute("SET time_zone = '-03:00'")
    cursor.close()

    return banco
