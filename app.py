import hmac
import hashlib
import os
import re
import secrets
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime
from urllib.parse import urlparse

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from mysql.connector import Error as ErroBanco
from werkzeug.exceptions import HTTPException
from werkzeug.middleware.proxy_fix import ProxyFix

import seguranca
from conexao import conectar
from servico_email import enviar_email

app = Flask(__name__)

# No Render, a variável RENDER existe automaticamente: é assim que o sistema
# sabe que está "no ar" (produção) e não rodando no seu computador.
EM_PRODUCAO = bool(os.environ.get("RENDER"))

# Chave usada para assinar a sessão. No computador existe um valor de teste;
# no Render a variável SECRET_KEY é obrigatória.
chave_secreta = os.environ.get("SECRET_KEY")

if not chave_secreta:
    if EM_PRODUCAO:
        raise RuntimeError(
            "Defina a variável de ambiente SECRET_KEY no Render "
            "(Environment > Add Environment Variable)."
        )
    chave_secreta = "almoxarifado-senai-chave-de-desenvolvimento"

app.secret_key = chave_secreta
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=EM_PRODUCAO,  # só envia o cookie por HTTPS no ar
)

if EM_PRODUCAO:
    # O Render fica "na frente" do sistema; isto faz o Flask enxergar o IP e
    # o HTTPS reais do visitante.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)


# ==================================================
# CONSTANTES DO PROJETO
# ==================================================

# Tipo do produto -> prefixo do código (PAP_01, LIM_01, INF_01, OUT_01)
TIPOS_PRODUTO = {
    "papelaria": "PAP",
    "limpeza": "LIM",
    "informatica": "INF",
    "outros": "OUT",
}

ROTULOS_TIPO = {
    "papelaria": "Papelaria",
    "limpeza": "Limpeza",
    "informatica": "Informática",
    "outros": "Outros",
}

SITUACOES_PRODUTO = ("disponível", "indisponível")
SITUACOES_LOTE = ("ativo", "inativo")
STATUS_PEDIDO = ("pendente", "aprovado", "rejeitado")

# Tipos de movimentação gravados na tabela movimentacoes.
MOV_INCLUSAO = "Inclusão"
MOV_EDICAO = "Edição"
MOV_INATIVACAO = "Inativação"
MOV_NOVO_LOTE = "Novo lote"

# Valores do filtro da página de movimentações -> tipo gravado no banco.
FILTRO_TIPOS_MOVIMENTACAO = {
    "inclusao": MOV_INCLUSAO,
    "edicao": MOV_EDICAO,
    "inativacao": MOV_INATIVACAO,
    "novo_lote": MOV_NOVO_LOTE,
}

# Data de validade: troque para False se quiser permitir deixar em branco.
VALIDADE_OBRIGATORIA = True
ANO_MINIMO = 2000
ANO_MAXIMO = 2100

LIMITE_QUANTIDADE = 999999
TAMANHO_NOME_PRODUTO = 150
TAMANHO_SETOR = 100
TAMANHO_LINK = 500

# Bloqueio simples de tentativas de login (por usuário + IP), guardado na memória.
TENTATIVAS_MAXIMAS = 5
BLOQUEIO_SEGUNDOS = 300
falhas_de_login = {}

# Hash usado só para gastar o mesmo tempo quando o usuário não existe.
HASH_FALSO = seguranca.gerar_hash("senha-inexistente")

# Páginas que podem ser abertas sem estar logado.
ENDPOINTS_PUBLICOS = {
    "login",
    "esqueci_senha",
    "redefinir_senha",
    "static",
}
ENDPOINTS_ADMIN = {"gerenciar_usuarios"}


# ==================================================
# BANCO DE DADOS
# ==================================================

@contextmanager
def abrir_banco():
    """
    Abre conexão e cursor e garante o fechamento no final.
    Se ocorrer erro, desfaz (rollback) e repassa o erro; o detalhe
    completo é registrado no terminal pelo tratador de erros abaixo.
    """
    banco = conectar()
    cursor = banco.cursor(dictionary=True)

    try:
        yield banco, cursor
    except Exception:
        banco.rollback()
        raise
    finally:
        cursor.close()
        banco.close()


def garantir_coluna_perfil(cursor):
    """Adiciona a coluna perfil sem apagar ou recriar a tabela de usuários."""
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = 'usuarios'
          AND column_name = 'perfil'
        """
    )
    resultado = cursor.fetchone()
    if not resultado or resultado["total"] == 0:
        cursor.execute(
            "ALTER TABLE usuarios ADD COLUMN perfil VARCHAR(20) NOT NULL DEFAULT 'colaborador'"
        )

    # Preserva os usuários existentes como colaboradores e reconhece a conta
    # administrativa já utilizada no projeto.
    cursor.execute(
        "UPDATE usuarios SET perfil = 'admin' WHERE LOWER(usuario) = 'admin'"
    )


def exigir_admin():
    """Bloqueia o acesso administrativo mesmo que alguém digite a URL."""
    if session.get("perfil") != "admin":
        abort(403)


# ==================================================
# FILTROS E DADOS COMUNS DOS TEMPLATES
# ==================================================

@app.template_filter("data_br")
def filtro_data_br(valor):
    if not valor:
        return "Não se aplica"
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%d/%m/%Y")
    return str(valor)


@app.template_filter("datahora_br")
def filtro_datahora_br(valor):
    if not valor:
        return "—"
    if isinstance(valor, (date, datetime)):
        return valor.strftime("%d/%m/%Y %H:%M")
    return str(valor)


@app.template_filter("rotulo_tipo")
def filtro_rotulo_tipo(valor):
    return ROTULOS_TIPO.get(valor, valor)


@app.template_filter("maiuscula_inicial")
def filtro_maiuscula_inicial(valor):
    valor = str(valor or "")
    return valor[:1].upper() + valor[1:]


@app.template_filter("classe_selo")
def filtro_classe_selo(valor):
    if valor in ("aprovado", "disponível", "ativo"):
        return "selo-ok"
    if valor == "pendente":
        return "selo-alerta"
    return "selo-erro"


@app.context_processor
def dados_comuns():
    return {
        "data_minima": f"{ANO_MINIMO}-01-01",
        "data_maxima": f"{ANO_MAXIMO}-12-31",
        "limite_quantidade": LIMITE_QUANTIDADE,
    }


# ==================================================
# VALIDAÇÕES
# ==================================================

def ler_data_validade(formulario):
    """
    Lê o campo data_validade (AAAA-MM-DD) e valida.
    Retorna (data, erro). O ano precisa ter exatamente 4 dígitos.
    """
    texto = formulario.get("data_validade", "").strip()

    if not texto:
        if VALIDADE_OBRIGATORIA:
            return None, "Informe a data de validade."
        return None, None

    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", texto):
        return None, (
            "Data de validade inválida. Use uma data com ano de quatro dígitos."
        )

    try:
        data = date.fromisoformat(texto)
    except ValueError:
        return None, "Data de validade inválida: essa data não existe."

    if not ANO_MINIMO <= data.year <= ANO_MAXIMO:
        return None, (
            f"A data de validade deve estar entre os anos "
            f"{ANO_MINIMO} e {ANO_MAXIMO}."
        )

    return data, None


def ler_inteiro(formulario, campo, rotulo, minimo, maximo=LIMITE_QUANTIDADE):
    """Lê um número inteiro do formulário. Retorna (valor, erro)."""
    texto = formulario.get(campo, "").strip()

    if not re.fullmatch(r"[0-9]+", texto):
        return None, f"{rotulo} inválida."

    valor = int(texto)

    if not minimo <= valor <= maximo:
        return None, f"{rotulo} deve estar entre {minimo} e {maximo}."

    return valor, None


def ler_texto(formulario, campo, rotulo, tamanho_maximo):
    """Lê um texto obrigatório do formulário. Retorna (texto, erro)."""
    texto = formulario.get(campo, "").strip()

    if not texto:
        return None, f"Informe: {rotulo}."

    if len(texto) > tamanho_maximo:
        return None, f"{rotulo} deve ter no máximo {tamanho_maximo} caracteres."

    return texto, None


def ler_link(formulario, obrigatorio):
    """Aceita apenas links http:// ou https://. Retorna (link, erro)."""
    link = formulario.get("link_produto", "").strip()

    if not link:
        if obrigatorio:
            return None, "Informe o link do produto novo."
        return None, None

    if len(link) > TAMANHO_LINK:
        return None, f"O link deve ter no máximo {TAMANHO_LINK} caracteres."

    partes = urlparse(link)

    if partes.scheme not in ("http", "https") or not partes.netloc:
        return None, "O link deve começar com http:// ou https://."

    return link, None


def buscar_produto(cursor, texto):
    """
    Encontra um produto cadastrado a partir do texto escolhido na lista
    ("PAP_01 - Nome"), do código digitado ou do nome exato.
    Retorna (produto, erro).
    """
    texto = (texto or "").strip()

    if not texto:
        return None, "Escolha um produto cadastrado."

    codigo = texto.split(" - ")[0].strip().upper()

    cursor.execute(
        """
        SELECT id, codigo, nome, situacao
        FROM produtos
        WHERE UPPER(codigo) = %s
        """,
        (codigo,)
    )
    produto = cursor.fetchone()

    if produto is None:
        cursor.execute(
            """
            SELECT id, codigo, nome, situacao
            FROM produtos
            WHERE nome = %s
            """,
            (texto,)
        )
        encontrados = cursor.fetchall()

        if len(encontrados) > 1:
            return None, (
                "Existe mais de um produto com esse nome. "
                "Escolha pelo código na lista."
            )

        if encontrados:
            produto = encontrados[0]

    if produto is None:
        return None, "Produto não encontrado. Escolha um item da lista."

    return produto, None


def listar_produtos_para_escolha(cursor, somente_disponiveis=False):
    consulta = "SELECT id, codigo, nome, situacao FROM produtos"

    if somente_disponiveis:
        consulta += " WHERE situacao = 'disponível'"

    cursor.execute(consulta + " ORDER BY nome")
    return cursor.fetchall()


# ==================================================
# MOVIMENTAÇÕES (REGISTRO AUTOMÁTICO)
# ==================================================

def registrar_movimentacao(
    cursor,
    tipo,
    descricao,
    produto_id=None,
    lote_id=None
):
    cursor.execute(
        """
        INSERT INTO movimentacoes
            (
                produto_id,
                lote_id,
                tipo_movimentacao,
                descricao,
                usuario_responsavel
            )
        VALUES (%s, %s, %s, %s, %s)
        """,
        (
            produto_id,
            lote_id,
            tipo,
            descricao,
            session.get("usuario", "Sistema")
        )
    )


def descrever_mudancas(mudancas):
    """mudancas: lista de (campo, valor_antigo, valor_novo)."""
    def formatar(valor):
        if isinstance(valor, date):
            return valor.strftime("%d/%m/%Y")
        return "(vazio)" if valor in (None, "") else str(valor)

    return "; ".join(
        f"{campo}: de {formatar(antigo)} para {formatar(novo)}"
        for campo, antigo, novo in mudancas
    )


# ==================================================
# LOGIN, SESSÃO E PROTEÇÃO DAS PÁGINAS
# ==================================================

# ==================================================
# PROTEÇÃO DOS FORMULÁRIOS (CSRF) E DE TENTATIVAS DE LOGIN
# ==================================================

def gerar_csrf():
    """Código secreto da sessão, enviado escondido em todo formulário POST."""
    if "csrf_token" not in session:
        session["csrf_token"] = secrets.token_hex(16)
    return session["csrf_token"]


app.jinja_env.globals["csrf_token"] = gerar_csrf


@app.before_request
def verificar_csrf():
    if request.method != "POST":
        return None

    enviado = request.form.get("csrf_token", "").encode()
    esperado = session.get("csrf_token", "").encode()

    if not esperado or not hmac.compare_digest(enviado, esperado):
        abort(400)

    return None


def chave_de_login(usuario):
    return f"{request.remote_addr}|{usuario.lower()}"


def segundos_de_bloqueio(chave):
    registro = falhas_de_login.get(chave)

    if registro and registro["ate"] > time.time():
        return int(registro["ate"] - time.time()) + 1

    return 0


def registrar_falha_de_login(chave):
    if len(falhas_de_login) > 5000:
        falhas_de_login.clear()

    registro = falhas_de_login.setdefault(chave, {"n": 0, "ate": 0})

    if registro["ate"] and registro["ate"] <= time.time():
        registro["n"] = 0
        registro["ate"] = 0

    registro["n"] += 1

    if registro["n"] >= TENTATIVAS_MAXIMAS:
        registro["ate"] = time.time() + BLOQUEIO_SEGUNDOS
        registro["n"] = 0


@app.before_request
def proteger_paginas():
    if request.endpoint is None or request.endpoint in ENDPOINTS_PUBLICOS:
        return None

    if "usuario_id" not in session:
        return redirect(url_for("login"))

    if request.endpoint in ENDPOINTS_ADMIN and session.get("perfil") != "admin":
        abort(403)

    # Troca de senha obrigatória: só libera alterar senha e sair.
    if session.get("troca_obrigatoria") and request.endpoint not in (
        "alterar_senha",
        "logout",
    ):
        flash("Você precisa alterar sua senha para continuar.", "info")
        return redirect(url_for("alterar_senha"))

    return None


@app.after_request
def nao_guardar_cache(resposta):
    # Evita que o botão "Voltar" mostre páginas internas após o logout.
    if "usuario_id" in session:
        resposta.headers["Cache-Control"] = "no-store"
    return resposta


@app.route("/login.html", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if "usuario_id" in session:
            return redirect(url_for("inicio"))
        return render_template("login.html", usuario="")

    usuario = request.form.get("usuario", "").strip()
    senha = request.form.get("senha", "")

    chave = chave_de_login(usuario)
    espera = segundos_de_bloqueio(chave)

    if espera:
        flash(
            f"Muitas tentativas incorretas. Aguarde {-(-espera // 60)} "
            f"minuto(s) e tente de novo.",
            "erro"
        )
        return render_template("login.html", usuario=usuario), 429

    with abrir_banco() as (banco, cursor):
        garantir_coluna_perfil(cursor)
        cursor.execute(
            """
            SELECT
                id,
                usuario,
                nome,
                senha_hash,
                ativo,
                perfil,
                motivo_troca,
                senha_alterada_em,
                ultimo_acesso
            FROM usuarios
            WHERE usuario = %s
            """,
            (usuario,)
        )
        conta = cursor.fetchone()

        if conta is None:
            seguranca.conferir_senha(HASH_FALSO, senha)
            senha_correta = False
        else:
            senha_correta = seguranca.conferir_senha(
                conta["senha_hash"], senha
            )

        if conta is None or not senha_correta or not conta["ativo"]:
            registrar_falha_de_login(chave)
            flash("Usuário ou senha inválidos.", "erro")
            return render_template("login.html", usuario=usuario), 401

        cursor.execute(
            "UPDATE usuarios SET ultimo_acesso = %s WHERE id = %s",
            (seguranca.agora(), conta["id"])
        )
        banco.commit()

    falhas_de_login.pop(chave, None)

    motivo = conta["motivo_troca"]

    if not motivo and seguranca.senha_expirada(conta["senha_alterada_em"]):
        motivo = seguranca.MOTIVO_SISTEMA

    session.clear()
    session["usuario_id"] = conta["id"]
    session["usuario"] = conta["usuario"]
    session["nome"] = conta["nome"]
    session["perfil"] = conta["perfil"]
    session["acesso_anterior"] = (
        conta["ultimo_acesso"].strftime("%d/%m/%Y %H:%M")
        if conta["ultimo_acesso"] else None
    )
    session["troca_obrigatoria"] = bool(motivo)
    session["motivo_troca"] = motivo

    if motivo:
        flash(f"Troca de senha obrigatória. Motivo: {motivo}.", "info")
        return redirect(url_for("alterar_senha"))

    return redirect(url_for("inicio"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão encerrada.", "sucesso")
    return redirect(url_for("login"))


@app.route("/esqueci_senha.html", methods=["GET", "POST"])
def esqueci_senha():
    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        usuario = request.form.get("usuario", "").strip()
        email = request.form.get("email", "").strip().lower()

        mensagem = (
            "Se os dados corresponderem a uma conta ativa, "
            "você receberá um link de recuperação no e-mail informado."
        )

        with abrir_banco() as (banco, cursor):
            cursor.execute(
                """
                SELECT id, nome, usuario, email
                FROM usuarios
                WHERE LOWER(nome) = LOWER(%s)
                  AND LOWER(usuario) = LOWER(%s)
                  AND LOWER(email) = LOWER(%s)
                  AND ativo = 1
                """,
                (nome, usuario, email)
            )
            conta = cursor.fetchone()

            if conta:
                token = secrets.token_urlsafe(32)
                token_hash = hashlib.sha256(
                    token.encode("utf-8")
                ).hexdigest()

                # Invalida códigos anteriores ainda não utilizados.
                cursor.execute(
                    """
                    DELETE FROM tokens_recuperacao
                    WHERE usuario_id = %s
                      AND usado_em IS NULL
                    """,
                    (conta["id"],)
                )

                cursor.execute(
                    """
                    INSERT INTO tokens_recuperacao
                        (usuario_id, token_hash, expira_em)
                    VALUES (%s, %s, DATE_ADD(NOW(), INTERVAL 30 MINUTE))
                    """,
                    (conta["id"], token_hash)
                )
                banco.commit()

                link = url_for(
                    "redefinir_senha",
                    token=token,
                    _external=True
                )

                try:
                    enviar_email(
                        email,
                        "Recuperação de senha - Almoxarifado",
                        (
                            f"Olá, {conta['nome']}!\n\n"
                            "Recebemos uma solicitação para redefinir a senha "
                            "da sua conta no Sistema de Almoxarifado.\n\n"
                            "Para criar uma nova senha, acesse o link abaixo:\n\n"
                            f"{link}\n\n"
                            "IMPORTANTE:\n"
                            "- O link é válido por 30 minutos.\n"
                            "- Ele só pode ser utilizado uma vez.\n\n"
                            "Se você não solicitou essa alteração, ignore este e-mail.\n\n"
                            "Atenciosamente,\n"
                            "Equipe do Almoxarifado"
                        )
                    )
                except Exception:
                    app.logger.exception(
                        "Falha ao enviar e-mail de recuperação."
                    )
                    cursor.execute(
                        """
                        DELETE FROM tokens_recuperacao
                        WHERE token_hash = %s
                        """,
                        (token_hash,)
                    )
                    banco.commit()

        flash(mensagem, "info")
        return redirect(url_for("esqueci_senha"))

    return render_template("esqueci_senha.html")


@app.route("/redefinir_senha/<token>", methods=["GET", "POST"])
def redefinir_senha(token):
    token_hash = hashlib.sha256(
        token.encode("utf-8")
    ).hexdigest()

    with abrir_banco() as (banco, cursor):
        cursor.execute(
            """
            SELECT t.id, t.usuario_id, u.usuario
            FROM tokens_recuperacao t
            INNER JOIN usuarios u ON u.id = t.usuario_id
            WHERE t.token_hash = %s
              AND t.usado_em IS NULL
              AND t.expira_em > NOW()
              AND u.ativo = 1
            """,
            (token_hash,)
        )
        recuperacao = cursor.fetchone()

    if recuperacao is None:
        flash(
            "Este link é inválido, já foi utilizado ou expirou. "
            "Solicite uma nova recuperação.",
            "erro"
        )
        return redirect(url_for("esqueci_senha"))

    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        nova_senha = request.form.get("nova_senha", "")
        confirmar = request.form.get("confirmar_senha", "")

        erro = None

        if usuario.lower() != recuperacao["usuario"].lower():
            erro = "O nome de usuário informado não corresponde à conta."
        elif nova_senha != confirmar:
            erro = "A confirmação da senha não corresponde."
        else:
            erro = seguranca.validar_nova_senha(nova_senha)

        if erro:
            flash(erro, "erro")
            return render_template(
                "redefinir_senha.html",
                token=token,
                usuario=usuario,
                tamanho_minimo=seguranca.TAMANHO_MINIMO_SENHA
            ), 400

        with abrir_banco() as (banco, cursor):
            # Confere novamente se o código ainda é válido.
            cursor.execute(
                """
                SELECT id
                FROM tokens_recuperacao
                WHERE id = %s
                  AND usado_em IS NULL
                  AND expira_em > NOW()
                """,
                (recuperacao["id"],)
            )

            if cursor.fetchone() is None:
                flash(
                    "Este link não está mais válido. Solicite outro.",
                    "erro"
                )
                return redirect(url_for("esqueci_senha"))

            cursor.execute(
                """
                UPDATE usuarios
                SET senha_hash = %s,
                    senha_alterada_em = %s,
                    motivo_troca = NULL
                WHERE id = %s
                """,
                (
                    seguranca.gerar_hash(nova_senha),
                    seguranca.agora(),
                    recuperacao["usuario_id"]
                )
            )

            cursor.execute(
                """
                UPDATE tokens_recuperacao
                SET usado_em = NOW()
                WHERE id = %s
                """,
                (recuperacao["id"],)
            )

            banco.commit()

        flash(
            "Senha redefinida com sucesso! Você já pode entrar no sistema.",
            "sucesso"
        )
        return redirect(url_for("login"))

    return render_template(
        "redefinir_senha.html",
        token=token,
        usuario=recuperacao["usuario"],
        tamanho_minimo=seguranca.TAMANHO_MINIMO_SENHA
    )




# ==================================================
# INÍCIO
# ==================================================

@app.route("/index.html")
@app.route("/")
def inicio():
    with abrir_banco() as (banco, cursor):
        totais = {}

        for nome, tabela in (
            ("produtos", "produtos"),
            ("lotes", "lotes"),
            ("pedidos", "pedidos_compra"),
            ("movimentacoes", "movimentacoes"),
        ):
            cursor.execute(f"SELECT COUNT(*) AS total FROM {tabela}")
            totais[nome] = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT COUNT(*) AS total
            FROM pedidos_compra
            WHERE status = 'pendente'
            """
        )
        totais["pedidos_pendentes"] = cursor.fetchone()["total"]

        cursor.execute(
            """
            SELECT
                m.tipo_movimentacao,
                m.usuario_responsavel,
                m.data_movimentacao,
                p.codigo AS codigo_produto,
                p.nome AS nome_produto
            FROM movimentacoes m
            LEFT JOIN produtos p ON m.produto_id = p.id
            ORDER BY m.data_movimentacao DESC, m.id DESC
            LIMIT 5
            """
        )
        ultimas = cursor.fetchall()

    return render_template("index.html", totais=totais, ultimas=ultimas)


# ==================================================
# PRODUTOS: LISTAR E CADASTRAR
# ==================================================

def validar_produto_novo(formulario):
    erros = []

    nome, erro = ler_texto(
        formulario, "nome", "Nome do produto", TAMANHO_NOME_PRODUTO
    )
    if erro:
        erros.append(erro)

    tipo = formulario.get("tipo", "").strip().lower()
    if tipo not in TIPOS_PRODUTO:
        erros.append("Selecione um tipo de produto válido.")

    validade, erro = ler_data_validade(formulario)
    if erro:
        erros.append(erro)

    quantidade, erro = ler_inteiro(
        formulario, "quantidade", "Quantidade", 1
    )
    if erro:
        erros.append(erro)

    dados = {
        "nome": nome,
        "tipo": tipo,
        "data_validade": validade,
        "quantidade": quantidade,
    }
    return dados, erros


def gerar_codigo_produto(cursor, tipo):
    prefixo = TIPOS_PRODUTO[tipo]

    cursor.execute(
        "SELECT codigo FROM produtos WHERE codigo LIKE %s",
        (prefixo + "_%",)
    )

    numeros = []

    for item in cursor.fetchall():
        encontrado = re.fullmatch(prefixo + r"_([0-9]+)", item["codigo"])
        if encontrado:
            numeros.append(int(encontrado.group(1)))

    return f"{prefixo}_{max(numeros, default=0) + 1:02d}"


@app.route("/produtos.html", methods=["GET", "POST"])
def produtos():
    status = 200

    with abrir_banco() as (banco, cursor):
        if request.method == "POST":
            dados, erros = validar_produto_novo(request.form)

            if not erros:
                codigo = gerar_codigo_produto(cursor, dados["tipo"])

                cursor.execute(
                    """
                    INSERT INTO produtos
                        (codigo, nome, tipo, data_validade, quantidade)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (
                        codigo,
                        dados["nome"],
                        dados["tipo"],
                        dados["data_validade"],
                        dados["quantidade"],
                    )
                )

                registrar_movimentacao(
                    cursor,
                    MOV_INCLUSAO,
                    f"Produto {codigo} - {dados['nome']} cadastrado "
                    f"(quantidade inicial: {dados['quantidade']})",
                    produto_id=cursor.lastrowid
                )

                banco.commit()

                flash(
                    f"Produto {codigo} cadastrado com sucesso.", "sucesso"
                )
                return redirect(url_for("produtos"))

            for erro in erros:
                flash(erro, "erro")

            status = 400

        cursor.execute("SELECT * FROM produtos ORDER BY id DESC")
        lista_produtos = cursor.fetchall()

    return render_template(
        "produtos.html",
        produtos=lista_produtos,
        form=request.form if request.method == "POST" else {}
    ), status


# ==================================================
# PRODUTOS: EDITAR
# ==================================================

@app.route("/editar_produto/<int:id>", methods=["GET", "POST"])
def editar_produto(id):
    status = 200

    with abrir_banco() as (banco, cursor):
        cursor.execute("SELECT * FROM produtos WHERE id = %s", (id,))
        produto = cursor.fetchone()

        if produto is None:
            abort(404)

        if request.method == "POST":
            erros = []

            nome, erro = ler_texto(
                request.form, "nome", "Nome do produto",
                TAMANHO_NOME_PRODUTO
            )
            if erro:
                erros.append(erro)

            validade, erro = ler_data_validade(request.form)
            if erro:
                erros.append(erro)

            quantidade, erro = ler_inteiro(
                request.form, "quantidade", "Quantidade", 0
            )
            if erro:
                erros.append(erro)

            situacao = request.form.get("situacao", "")
            if situacao not in SITUACOES_PRODUTO:
                erros.append("Situação inválida.")

            if not erros:
                mudancas = []

                if nome != produto["nome"]:
                    mudancas.append(("nome", produto["nome"], nome))
                if validade != produto["data_validade"]:
                    mudancas.append(
                        ("validade", produto["data_validade"], validade)
                    )
                if quantidade != produto["quantidade"]:
                    mudancas.append(
                        ("quantidade", produto["quantidade"], quantidade)
                    )
                if situacao != produto["situacao"]:
                    mudancas.append(
                        ("situação", produto["situacao"], situacao)
                    )

                if not mudancas:
                    flash("Nenhuma alteração foi feita.", "info")
                    return redirect(url_for("produtos"))

                cursor.execute(
                    """
                    UPDATE produtos
                    SET nome = %s,
                        data_validade = %s,
                        quantidade = %s,
                        situacao = %s
                    WHERE id = %s
                    """,
                    (nome, validade, quantidade, situacao, id)
                )

                inativou = (
                    situacao == "indisponível"
                    and produto["situacao"] != "indisponível"
                )

                registrar_movimentacao(
                    cursor,
                    MOV_INATIVACAO if inativou else MOV_EDICAO,
                    f"Produto {produto['codigo']} - {nome} editado ("
                    f"{descrever_mudancas(mudancas)})",
                    produto_id=id
                )

                banco.commit()

                flash(
                    f"Produto {produto['codigo']} atualizado com sucesso.",
                    "sucesso"
                )
                return redirect(url_for("produtos"))

            for erro in erros:
                flash(erro, "erro")

            status = 400

    return render_template(
        "editar_produto.html",
        produto=produto,
        form=request.form if request.method == "POST" else {}
    ), status


# ==================================================
# LOTES: LISTAR
# ==================================================

@app.route("/lotes.html")
def lotes():
    with abrir_banco() as (banco, cursor):
        cursor.execute(
            """
            SELECT
                l.id,
                l.numero_lote,
                l.quantidade,
                l.data_validade,
                l.situacao,
                l.data_cadastro,
                p.codigo AS codigo_produto,
                p.nome AS nome_produto
            FROM lotes l
            INNER JOIN produtos p ON l.produto_id = p.id
            ORDER BY l.id DESC
            """
        )
        lista_lotes = cursor.fetchall()

    return render_template("lotes.html", lotes=lista_lotes)


# ==================================================
# LOTES: CADASTRAR
# ==================================================

def gerar_numero_lote(cursor):
    cursor.execute("SELECT numero_lote FROM lotes")

    numeros = []

    for item in cursor.fetchall():
        encontrado = re.fullmatch(r"LOTE_([0-9]+)", item["numero_lote"])
        if encontrado:
            numeros.append(int(encontrado.group(1)))

    return f"LOTE_{max(numeros, default=0) + 1:02d}"


@app.route("/novo_lote.html", methods=["GET", "POST"])
def novo_lote():
    status = 200

    with abrir_banco() as (banco, cursor):
        if request.method == "POST":
            erros = []

            produto, erro = buscar_produto(
                cursor, request.form.get("produto", "")
            )
            if erro:
                erros.append(erro)
            elif produto["situacao"] != "disponível":
                erros.append(
                    "Esse produto está indisponível e não pode receber lotes."
                )

            quantidade, erro = ler_inteiro(
                request.form, "quantidade", "Quantidade", 1
            )
            if erro:
                erros.append(erro)

            validade, erro = ler_data_validade(request.form)
            if erro:
                erros.append(erro)

            if not erros:
                numero_lote = gerar_numero_lote(cursor)

                cursor.execute(
                    """
                    INSERT INTO lotes
                        (numero_lote, produto_id, quantidade, data_validade)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (numero_lote, produto["id"], quantidade, validade)
                )

                registrar_movimentacao(
                    cursor,
                    MOV_NOVO_LOTE,
                    f"Lote {numero_lote} criado para "
                    f"{produto['codigo']} - {produto['nome']} "
                    f"(quantidade: {quantidade})",
                    produto_id=produto["id"],
                    lote_id=cursor.lastrowid
                )

                banco.commit()

                flash(f"Lote {numero_lote} cadastrado com sucesso.", "sucesso")
                return redirect(url_for("lotes"))

            for erro in erros:
                flash(erro, "erro")

            status = 400

        lista_produtos = listar_produtos_para_escolha(
            cursor, somente_disponiveis=True
        )

    return render_template(
        "novo_lote.html",
        produtos=lista_produtos,
        form=request.form if request.method == "POST" else {}
    ), status


# ==================================================
# LOTES: EDITAR
# ==================================================

@app.route("/editar_lote/<int:id>", methods=["GET", "POST"])
def editar_lote(id):
    status = 200

    with abrir_banco() as (banco, cursor):
        cursor.execute(
            """
            SELECT
                l.id,
                l.produto_id,
                l.numero_lote,
                l.quantidade,
                l.data_validade,
                l.situacao,
                p.codigo AS codigo_produto,
                p.nome AS nome_produto
            FROM lotes l
            INNER JOIN produtos p ON l.produto_id = p.id
            WHERE l.id = %s
            """,
            (id,)
        )
        lote = cursor.fetchone()

        if lote is None:
            abort(404)

        if request.method == "POST":
            erros = []

            quantidade, erro = ler_inteiro(
                request.form, "quantidade", "Quantidade", 0
            )
            if erro:
                erros.append(erro)

            validade, erro = ler_data_validade(request.form)
            if erro:
                erros.append(erro)

            situacao = request.form.get("situacao", "")
            if situacao not in SITUACOES_LOTE:
                erros.append("Situação inválida.")

            if not erros:
                mudancas = []

                if quantidade != lote["quantidade"]:
                    mudancas.append(
                        ("quantidade", lote["quantidade"], quantidade)
                    )
                if validade != lote["data_validade"]:
                    mudancas.append(
                        ("validade", lote["data_validade"], validade)
                    )
                if situacao != lote["situacao"]:
                    mudancas.append(
                        ("situação", lote["situacao"], situacao)
                    )

                if not mudancas:
                    flash("Nenhuma alteração foi feita.", "info")
                    return redirect(url_for("lotes"))

                cursor.execute(
                    """
                    UPDATE lotes
                    SET quantidade = %s,
                        data_validade = %s,
                        situacao = %s
                    WHERE id = %s
                    """,
                    (quantidade, validade, situacao, id)
                )

                inativou = situacao == "inativo" and lote["situacao"] != "inativo"

                registrar_movimentacao(
                    cursor,
                    MOV_INATIVACAO if inativou else MOV_EDICAO,
                    f"Lote {lote['numero_lote']} editado ("
                    f"{descrever_mudancas(mudancas)})",
                    produto_id=lote["produto_id"],
                    lote_id=id
                )

                banco.commit()

                flash(
                    f"Lote {lote['numero_lote']} atualizado com sucesso.",
                    "sucesso"
                )
                return redirect(url_for("lotes"))

            for erro in erros:
                flash(erro, "erro")

            status = 400

    return render_template(
        "editar_lote.html",
        lote=lote,
        form=request.form if request.method == "POST" else {}
    ), status


# ==================================================
# PEDIDOS DE COMPRA
# ==================================================

def validar_pedido(cursor, formulario):
    """Retorna (dados, erros) para um novo pedido de compra."""
    erros = []
    produto_id = None
    nome_produto = None

    produto_novo = formulario.get("produto_novo", "")

    if produto_novo not in ("sim", "nao"):
        erros.append("Informe se o produto é novo ou já cadastrado.")

    elif produto_novo == "sim":
        nome_produto, erro = ler_texto(
            formulario, "nome_produto", "Nome do produto",
            TAMANHO_NOME_PRODUTO
        )
        if erro:
            erros.append(erro)

    else:
        produto, erro = buscar_produto(
            cursor, formulario.get("produto", "")
        )
        if erro:
            erros.append(erro)
        else:
            produto_id = produto["id"]
            nome_produto = produto["nome"]

    quantidade, erro = ler_inteiro(
        formulario, "quantidade", "Quantidade solicitada", 1
    )
    if erro:
        erros.append(erro)

    setor, erro = ler_texto(
        formulario, "setor", "Setor solicitante", TAMANHO_SETOR
    )
    if erro:
        erros.append(erro)

    # O link é obrigatório para produto novo e opcional para os demais.
    link, erro = ler_link(formulario, obrigatorio=(produto_novo == "sim"))
    if erro:
        erros.append(erro)

    dados = {
        "produto_id": produto_id,
        "nome_produto": nome_produto,
        "produto_novo": 1 if produto_novo == "sim" else 0,
        "quantidade": quantidade,
        "setor": setor,
        "link_produto": link,
    }
    return dados, erros


@app.route("/pedidos.html", methods=["GET", "POST"])
def pedidos():
    status_http = 200

    with abrir_banco() as (banco, cursor):
        if request.method == "POST":
            dados, erros = validar_pedido(cursor, request.form)

            if not erros:
                # O número definitivo (PED_01...) é gerado a partir do id.
                # Um valor temporário único evita conflito na inserção.
                cursor.execute(
                    """
                    INSERT INTO pedidos_compra
                        (
                            numero,
                            produto_id,
                            nome_produto,
                            produto_novo,
                            quantidade,
                            setor,
                            link_produto,
                            status,
                            solicitante
                        )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, 'pendente', %s)
                    """,
                    (
                        uuid.uuid4().hex[:20],
                        dados["produto_id"],
                        dados["nome_produto"],
                        dados["produto_novo"],
                        dados["quantidade"],
                        dados["setor"],
                        dados["link_produto"],
                        session.get("usuario"),
                    )
                )

                pedido_id = cursor.lastrowid
                numero = f"PED_{pedido_id:02d}"

                cursor.execute(
                    "UPDATE pedidos_compra SET numero = %s WHERE id = %s",
                    (numero, pedido_id)
                )

                banco.commit()

                flash(f"Pedido {numero} registrado com sucesso.", "sucesso")
                return redirect(url_for("pedidos"))

            for erro in erros:
                flash(erro, "erro")

            status_http = 400

        filtro_status = request.args.get("status", "")

        if filtro_status in STATUS_PEDIDO:
            cursor.execute(
                """
                SELECT * FROM pedidos_compra
                WHERE status = %s
                ORDER BY id DESC
                """,
                (filtro_status,)
            )
        else:
            filtro_status = ""
            cursor.execute(
                "SELECT * FROM pedidos_compra ORDER BY id DESC"
            )

        lista_pedidos = cursor.fetchall()
        lista_produtos = listar_produtos_para_escolha(cursor)

    return render_template(
        "pedidos.html",
        pedidos=lista_pedidos,
        produtos=lista_produtos,
        filtro_status=filtro_status,
        status_pedido=STATUS_PEDIDO,
        form=request.form if request.method == "POST" else {}
    ), status_http


@app.route("/visualizar_pedido/<int:id>", methods=["GET", "POST"])
def visualizar_pedido(id):
    status_http = 200

    with abrir_banco() as (banco, cursor):
        cursor.execute(
            """
            SELECT
                p.*,
                pr.codigo AS codigo_produto
            FROM pedidos_compra p
            LEFT JOIN produtos pr ON p.produto_id = pr.id
            WHERE p.id = %s
            """,
            (id,)
        )
        pedido = cursor.fetchone()

        if pedido is None:
            abort(404)

        if request.method == "POST":
            novo_status = request.form.get("status", "")

            if novo_status not in STATUS_PEDIDO:
                flash("Situação do pedido inválida.", "erro")
                status_http = 400

            elif novo_status == pedido["status"]:
                flash("O pedido já está com essa situação.", "info")
                return redirect(url_for("visualizar_pedido", id=id))

            else:
                cursor.execute(
                    """
                    UPDATE pedidos_compra
                    SET status = %s,
                        data_atualizacao = CURRENT_TIMESTAMP,
                        atualizado_por = %s
                    WHERE id = %s
                    """,
                    (novo_status, session.get("usuario"), id)
                )
                banco.commit()

                flash(
                    f"Pedido {pedido['numero']} agora está "
                    f"{novo_status}.",
                    "sucesso"
                )
                return redirect(url_for("visualizar_pedido", id=id))

    return render_template(
        "visualizar_pedido.html",
        pedido=pedido,
        status_pedido=STATUS_PEDIDO
    ), status_http


# ==================================================
# HISTÓRICO DE MOVIMENTAÇÕES
# ==================================================

@app.route("/movimentacoes.html")
def movimentacoes():
    filtro_produto = request.args.get("produto", "").strip()
    filtro_tipo = request.args.get("tipo", "")

    condicoes = []
    parametros = []

    if filtro_produto:
        condicoes.append("(p.nome LIKE %s OR p.codigo LIKE %s)")
        parametros.extend([f"%{filtro_produto}%"] * 2)

    if filtro_tipo in FILTRO_TIPOS_MOVIMENTACAO:
        condicoes.append("m.tipo_movimentacao = %s")
        parametros.append(FILTRO_TIPOS_MOVIMENTACAO[filtro_tipo])
    else:
        filtro_tipo = ""

    where = ("WHERE " + " AND ".join(condicoes)) if condicoes else ""

    with abrir_banco() as (banco, cursor):
        cursor.execute(
            f"""
            SELECT
                m.id,
                m.produto_id,
                m.lote_id,
                m.tipo_movimentacao,
                m.descricao,
                m.usuario_responsavel,
                m.data_movimentacao,
                p.codigo AS codigo_produto,
                p.nome AS nome_produto,
                l.numero_lote
            FROM movimentacoes m
            LEFT JOIN produtos p ON m.produto_id = p.id
            LEFT JOIN lotes l ON m.lote_id = l.id
            {where}
            ORDER BY m.data_movimentacao DESC, m.id DESC
            """,
            tuple(parametros)
        )
        lista_movimentacoes = cursor.fetchall()

    return render_template(
        "movimentacoes.html",
        movimentacoes=lista_movimentacoes,
        filtro_produto=filtro_produto,
        filtro_tipo=filtro_tipo
    )


# ==================================================
# GERENCIAMENTO DE USUÁRIOS (SOMENTE ADMINISTRADOR)
# ==================================================

@app.route("/gerenciar_usuarios.html", methods=["GET", "POST"])
def gerenciar_usuarios():
    exigir_admin()
    status = 200

    if request.method == "POST":
        usuario_novo = request.form.get("usuario", "").strip()
        nome_novo = request.form.get("nome", "").strip()
        email_novo = request.form.get("email", "").strip().lower()
        senha_nova = request.form.get("senha", "")
        perfil_novo = request.form.get("perfil", "colaborador").strip()

        erro = None
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,50}", usuario_novo):
            erro = "O usuário deve ter de 3 a 50 caracteres: letras, números, ponto, _ ou -."
        elif not nome_novo or len(nome_novo) > 100:
            erro = "Informe um nome com até 100 caracteres."
        elif not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email_novo):
            erro = "Informe um endereço de e-mail válido."    
        elif perfil_novo not in ("admin", "colaborador"):
            erro = "Selecione um perfil válido."
        else:
            erro = seguranca.validar_nova_senha(senha_nova)

        if erro:
            flash(erro, "erro")
            status = 400
        else:
            with abrir_banco() as (banco, cursor):
                cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", (usuario_novo,))
                if cursor.fetchone():
                    flash("Esse nome de usuário já está cadastrado.", "erro")
                    status = 400
                else:
                    cursor.execute(
                        """
                        INSERT INTO usuarios
                            (usuario, nome, email, senha_hash, ativo, perfil, motivo_troca, senha_alterada_em)
                        VALUES (%s, %s, %s, %s, 1, %s, %s, %s)
                        """,
                        (
                            usuario_novo,
                            nome_novo,
                            email_novo,
                            seguranca.gerar_hash(senha_nova),
                            perfil_novo,
                            seguranca.MOTIVO_SISTEMA,
                            seguranca.agora(),
                        )
                    )
                    banco.commit()
                    flash(
                        f"Usuário '{usuario_novo}' criado. No primeiro acesso, será solicitada a troca da senha.",
                        "sucesso",
                    )
                    return redirect(url_for("gerenciar_usuarios"))

    with abrir_banco() as (banco, cursor):
        garantir_coluna_perfil(cursor)
        banco.commit()
        cursor.execute(
            """
            SELECT id, usuario, nome, perfil, ativo, data_criacao
            FROM usuarios
            ORDER BY nome, usuario
            """
        )
        usuarios_cadastrados = cursor.fetchall()

    return render_template(
        "gerenciar_usuarios.html",
        usuarios=usuarios_cadastrados,
        tamanho_minimo=seguranca.TAMANHO_MINIMO_SENHA,
    ), status


# ==================================================
# USUÁRIO E SENHA
# ==================================================

@app.route("/usuario.html")
def usuario():
    with abrir_banco() as (banco, cursor):
        cursor.execute(
            """
            SELECT usuario, nome, senha_alterada_em
            FROM usuarios
            WHERE id = %s
            """,
            (session["usuario_id"],)
        )
        conta = cursor.fetchone()

    if conta is None:
        session.clear()
        return redirect(url_for("login"))

    dias_restantes = max(
        seguranca.DIAS_VALIDADE_SENHA
        - seguranca.dias_desde_troca(conta["senha_alterada_em"]),
        0
    )

    return render_template(
        "usuario.html",
        conta=conta,
        acesso_anterior=session.get("acesso_anterior"),
        dias_restantes=dias_restantes
    )


@app.route("/alterar_senha.html", methods=["GET", "POST"])
def alterar_senha():
    status = 200

    if request.method == "POST":
        senha_atual = request.form.get("senha_atual", "")
        nova_senha = request.form.get("nova_senha", "")
        confirmar = request.form.get("confirmar_senha", "")

        with abrir_banco() as (banco, cursor):
            cursor.execute(
                "SELECT senha_hash FROM usuarios WHERE id = %s",
                (session["usuario_id"],)
            )
            conta = cursor.fetchone()

            if conta is None:
                session.clear()
                return redirect(url_for("login"))

            erro = None

            if not seguranca.conferir_senha(conta["senha_hash"], senha_atual):
                erro = "A senha atual está incorreta."
            elif nova_senha != confirmar:
                erro = "A confirmação não é igual à nova senha."
            else:
                erro = seguranca.validar_nova_senha(nova_senha)

                if erro is None and nova_senha == senha_atual:
                    erro = "A nova senha deve ser diferente da atual."

            if erro is None:
                cursor.execute(
                    """
                    UPDATE usuarios
                    SET senha_hash = %s,
                        senha_alterada_em = %s,
                        motivo_troca = NULL
                    WHERE id = %s
                    """,
                    (
                        seguranca.gerar_hash(nova_senha),
                        seguranca.agora(),
                        session["usuario_id"],
                    )
                )
                banco.commit()

                session["troca_obrigatoria"] = False
                session["motivo_troca"] = None

                flash("Senha alterada com sucesso.", "sucesso")
                return redirect(url_for("inicio"))

        flash(erro, "erro")
        status = 400

    return render_template(
        "alterar_senha.html",
        motivo=session.get("motivo_troca") if session.get("troca_obrigatoria") else None,
        tamanho_minimo=seguranca.TAMANHO_MINIMO_SENHA
    ), status


# ==================================================
# TRATAMENTO DE ERROS
# ==================================================

@app.errorhandler(HTTPException)
def erro_http(erro):
    mensagens = {
        400: (
            "A página expirou ou o formulário é inválido. "
            "Volte, recarregue a página e tente de novo."
        ),
        404: "Página ou registro não encontrado.",
        405: "Ação não permitida para esta página.",
    }
    mensagem = mensagens.get(erro.code, erro.description)
    return render_template(
        "erro.html", codigo=erro.code, mensagem=mensagem
    ), erro.code


@app.errorhandler(ErroBanco)
def erro_de_banco(erro):
    app.logger.exception("Erro de banco em %s %s", request.method, request.path)
    return render_template(
        "erro.html",
        codigo=500,
        mensagem=(
            "Não foi possível usar o banco de dados. Confira se ele está ligado "
            "(no computador: MySQL/XAMPP; na nuvem: painel do Aiven) e tente de "
            "novo em instantes. Os detalhes foram registrados no terminal."
        )
    ), 500


@app.errorhandler(Exception)
def erro_inesperado(erro):
    # Erros de banco e outros problemas: o detalhe completo vai para o terminal.
    app.logger.exception("Erro inesperado em %s %s", request.method, request.path)
    return render_template(
        "erro.html",
        codigo=500,
        mensagem=(
            "Ocorreu um erro ao processar a solicitação. "
            "Os detalhes foram registrados no terminal."
        )
    ), 500


# ==================================================
# EXECUTAR O SISTEMA
# ==================================================

if __name__ == "__main__":
    app.run(debug=True)