# Sistema de Almoxarifado — Guia para quem nunca fez isso

Este guia tem 3 partes. Faça só o que precisar:

- **PARTE A** — usar o sistema no seu computador (para estudar e para apresentar).
- **PARTE B** — colocar o sistema na internet, de graça (Aiven + Render).
- **PARTE C** — dia a dia: backup, atualizar, problemas comuns.

> Antes de qualquer coisa: **faça uma cópia da pasta do seu projeto** (copiar e colar em outro lugar).

---

## O que tem dentro da pasta

| Arquivo | Para que serve |
|---|---|
| `1_INSTALAR.bat` | Instala o que o sistema precisa (uma vez só) |
| `2_TESTAR_CONEXAO.bat` | Testa se o sistema consegue falar com o banco |
| `3_CRIAR_USUARIO.bat` | Cria o seu usuário e senha de acesso |
| `4_INICIAR_SISTEMA.bat` | Liga o sistema |
| `5_REDEFINIR_SENHA.bat` | Para quando alguém esqueceu a senha |
| `criar_banco_completo.sql` | Cria o banco no MySQL do **seu computador** |
| `banco_producao.sql` | Cria as tabelas no banco **online** (Aiven) |
| `app.py`, `templates`, `static`... | O sistema em si (não precisa mexer) |

Os arquivos `.bat` abrem com **duplo clique**. Eles evitam aquele erro do PowerShell
("a execução de scripts foi desabilitada").

---

# PARTE A — Usar no seu computador

## A1. Ligar o MySQL
Abra o **XAMPP** e clique em **Start** no MySQL (deve ficar verde). Sem isso, nada funciona.
O sistema espera o MySQL na **porta 3307**, usuário `root` e senha `root`
(são os valores que você já usava).

## A2. Criar o banco (só na primeira vez)
1. Abra o **MySQL Workbench** e entre na sua conexão local.
2. Menu **File → Open SQL Script** e escolha `criar_banco_completo.sql`.
3. Clique no **primeiro raio** (o que executa o script inteiro).
4. Embaixo deve aparecer uma lista com **5 tabelas**: `lotes`, `movimentacoes`, `pedidos_compra`, `produtos`, `usuarios`.

Esse arquivo **não apaga nada**. Se você já tem o banco, pode executar de novo sem medo.

## A3. Instalar
Dê **duplo clique** em `1_INSTALAR.bat`. Espere terminar (pode demorar alguns minutos).
Se aparecer erro em vermelho, copie a mensagem e peça ajuda.

> Se a pasta `.venv` veio de outro computador ou de outra pasta, apague-a e rode o `1_INSTALAR.bat` de novo.

## A4. Testar a conexão
Duplo clique em `2_TESTAR_CONEXAO.bat`. Deve aparecer "Conexão com o MySQL realizada com sucesso!".

## A5. Criar seu usuário
1. Duplo clique em `3_CRIAR_USUARIO.bat`.
2. Digite um **nome de usuário** (ex.: `admin`) e aperte Enter.
3. Digite seu **nome completo** e aperte Enter.
4. Digite a **senha** e aperte Enter. **Nada aparece na tela enquanto você digita. Isso é normal.**
5. Digite a mesma senha de novo e aperte Enter.

Regras da senha: **mínimo 8 caracteres e pelo menos 1 caractere especial** (`!`, `@`, `#`, `$`, `-`...).
Exemplo: `Almox@2026`. Anote a senha!

Deve aparecer "Usuário ... criado com sucesso".

## A6. Ligar o sistema
1. Duplo clique em `4_INICIAR_SISTEMA.bat`. Uma janela preta abre e **fica aberta**. Isso é normal.
2. Aguarde aparecer `Running on http://127.0.0.1:5000`.
3. Abra o navegador (Chrome, Edge...) e digite: **http://127.0.0.1:5000**
4. Entre com o usuário e a senha que você criou.

Para desligar: feche a janela preta.

## A7. Como usar cada tela (passo a passo)

**Produtos**
1. Menu **Produtos**.
2. Preencha nome, tipo, data de validade e quantidade e clique em **Cadastrar produto**.
3. O código nasce sozinho: `PAP_01` (papelaria), `LIM_01` (limpeza), `INF_01` (informática), `OUT_01` (outros).
4. Para mudar nome, validade, quantidade ou situação: **Editar** na linha do produto. O tipo não muda (o código depende dele).

**Lotes**
1. Menu **Lotes → Cadastrar novo lote**.
2. No campo Produto, comece a digitar o **nome ou o código** e escolha na lista que aparece.
3. Informe quantidade e validade. O número `LOTE_01`, `LOTE_02`... nasce sozinho.
4. **Editar** muda quantidade, validade e situação.

**Pedidos de compra**
1. Menu **Pedidos de compra**.
2. "É um produto novo?" — **Sim**: digite o nome e informe o link da loja (obrigatório, começando com `https://`). **Não**: escolha o produto já cadastrado.
3. Preencha quantidade e setor e clique em **Enviar pedido**.
4. Para aprovar ou rejeitar: **Visualizar** na linha do pedido → escolha a situação → **Salvar situação**.

**Movimentações**
Mostra tudo o que foi feito (inclusão, edição, novo lote, inativação), com data, hora e usuário.
Dá para filtrar por nome/código do produto e por tipo.

**Usuário / Alterar senha**
Menu **Usuário → Alterar senha**. A senha precisa ser trocada **a cada 60 dias**: depois disso o próprio sistema pede a troca ao entrar.
Se alguém esquecer a senha, use `5_REDEFINIR_SENHA.bat`: ele define uma senha temporária e a pessoa troca ao entrar.

**Sair:** botão **Sair** no menu da esquerda.

---

# PARTE B — Colocar na internet, de graça (Aiven + Render)

Você vai usar **dois serviços gratuitos**: o **Aiven** guarda o banco MySQL e o **Render** roda o site.

**Limitações (leia antes):**
- O site no Render "dorme" depois de uns 15 minutos sem acesso. O primeiro acesso depois disso leva cerca de 1 minuto. **Abra o site uns minutos antes de apresentar.**
- O Aiven gratuito pode desligar o banco se ficar sem uso. Se o site mostrar erro de banco, entre no painel do Aiven e **ligue o serviço**.
- Os planos gratuitos mudam. Confira nos sites.
- Quem tiver o endereço do site consegue abrir a tela de login. Use senha forte.

## B1. Criar o banco no Aiven
1. Entre em **console.aiven.io** e crie uma conta (não precisa de cartão).
2. Crie um **serviço novo**, escolha **MySQL** e o plano **Free**. Crie.
3. Espere ficar **Running**. Na tela do serviço (Overview), **anote** (cole num bloco de notas):
   **Host**, **Port**, **User**, **Password** e o **Database** (geralmente `defaultdb`).

## B2. Criar as tabelas no banco online
1. No **MySQL Workbench**, crie uma conexão nova (o `+` ao lado de "MySQL Connections") com o Host, a Port, o User e a Password do Aiven.
2. Se não conectar, na aba **SSL** da conexão escolha **Require** e tente de novo.
3. Conectado, **File → Open SQL Script → `banco_producao.sql`**.
4. No painel esquerdo, clique com o botão direito no banco (`defaultdb`) → **Set as Default Schema**.
5. Execute só a **PARTE 1** do arquivo (da primeira linha até `SHOW TABLES;`). Pode **selecionar esse trecho** e clicar no raio.
   **Não execute a PARTE 2** (o usuário já vem do Aiven).
6. Deve aparecer a lista com 5 tabelas.

## B3. Criar seu usuário no banco online
Abra o **PowerShell** na pasta do projeto e cole **linha por linha**, trocando pelos seus dados:

```
$env:DB_HOST="COLE_O_HOST"
$env:DB_PORT="COLE_A_PORTA"
$env:DB_USER="COLE_O_USER"
$env:DB_PASSWORD="COLE_A_SENHA"
$env:DB_NAME="defaultdb"
.venv\Scripts\python.exe criar_usuario.py
```

Responda às perguntas como na Parte A5. Quando fechar essa janela, o computador volta a usar o banco local.

## B4. Colocar o código no GitHub
1. Entre em **github.com** e crie um repositório novo (**New repository**), com qualquer nome.
2. Clique em **uploading an existing file** e arraste os arquivos e pastas do projeto.
3. **NÃO envie** a pasta `.venv`, a pasta `__pycache__` nem nenhum arquivo com senhas.
4. Clique em **Commit changes**.

## B5. Criar o site no Render
1. Entre em **render.com** → **New → Web Service** → conecte sua conta do GitHub e escolha o repositório.
2. Preencha:
   - **Language:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Instance Type:** Free
3. Em **Environment Variables**, adicione (nome → valor):

| Nome | Valor |
|---|---|
| `SECRET_KEY` | um texto bem longo e aleatório que você inventar |
| `DB_HOST` | o Host do Aiven |
| `DB_PORT` | a Port do Aiven |
| `DB_USER` | o User do Aiven |
| `DB_PASSWORD` | a Password do Aiven |
| `DB_NAME` | `defaultdb` |

4. Clique em **Create Web Service**, espere o deploy terminar (aparece "Live") e abra o endereço que o Render mostrar.
5. Entre com o usuário que você criou no passo B3.

---

# PARTE C — Dia a dia

## Backup do banco (faça antes da apresentação e de vez em quando)
No Workbench: **Server → Data Export** → escolha o banco → **Export to Self-Contained File** → **Start Export**. Guarde o arquivo.
**Nunca** importe um backup antigo em cima de um banco com dados novos: ele pode apagar tabelas.

## Atualizar o site depois de mudar o código
No GitHub, envie os arquivos alterados (**Add file → Upload files**) e clique em **Commit changes**. O Render atualiza sozinho.

## Problemas comuns

| O que aparece | O que fazer |
|---|---|
| "a execução de scripts foi desabilitada" | Use os arquivos `.bat` (duplo clique) em vez do PowerShell |
| `Unknown database 'almoxarifado'` | O banco não existe: faça o passo A2 |
| `Table '...usuarios' doesn't exist` | As tabelas não existem: refaça o A2 (local) ou o B2 (online) |
| `Can't connect ... 3307` / `Access denied` | O MySQL do XAMPP não está ligado (A1), ou a porta/senha do seu MySQL é outra |
| A janela do `4_INICIAR_SISTEMA.bat` fecha sozinha | Abra o PowerShell na pasta e rode `.venv\Scripts\python.exe app.py` para ver a mensagem de erro |
| "Address already in use" | O sistema já está ligado em outra janela. Feche-a |
| "Usuário ou senha inválidos" | Confira usuário e senha. Se esqueceu, use `5_REDEFINIR_SENHA.bat` |
| "Muitas tentativas incorretas" | Aguarde 5 minutos. O sistema bloqueia depois de 5 erros seguidos |
| "A página expirou ou o formulário é inválido" | Volte, recarregue a página (F5) e envie de novo. Acontece se a página ficou muito tempo aberta |
| "Você precisa alterar sua senha" | É normal depois de 60 dias ou de uma redefinição: troque a senha |
| Data de validade recusada | Use uma data real, com ano de 4 dígitos, entre 2000 e 2100 |
| Site online demora ~1 minuto | É o plano gratuito do Render "acordando". Espere |
| Site online mostra "não foi possível usar o banco de dados" | Entre no painel do Aiven e ligue o serviço. Veja também os **Logs** no Render |
| Erro `RuntimeError: Defina a variável SECRET_KEY` nos logs do Render | Faltou a variável `SECRET_KEY` (passo B5) |
| Horários 3 horas diferentes | Não deveria acontecer: o sistema usa o horário de Brasília. Se acontecer, avise |

## Segurança básica
- Nunca coloque senhas dentro dos arquivos nem no GitHub. Use as variáveis de ambiente.
- O sistema bloqueia tentativas repetidas de login e protege os formulários, mas é um projeto escolar: não guarde dados sensíveis reais nele.
- Troque a senha de vez em quando e faça backup.


ATUALIZAÇÃO - GERENCIAMENTO DE USUÁRIOS
--------------------------------------
Depois de substituir os arquivos pela versão atualizada e iniciar o sistema,
a coluna `perfil` será adicionada automaticamente à tabela `usuarios` no
primeiro login. A conta com nome de usuário `admin` será reconhecida como
Administradora. Nenhuma tabela ou registro existente será apagado.

Para cadastrar pessoas: entre com a conta admin, abra “Gerenciar usuários”
no menu lateral, preencha os dados e clique em “Cadastrar usuário”. A senha
inicial será trocada pelo próprio usuário no primeiro acesso.
