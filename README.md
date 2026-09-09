# Rotina

Aplicação Django para organizar tarefas do dia a dia: cadastro, painel de
acompanhamento, calendário e lembrete configurável (se e com quanto tempo
de antecedência avisar antes do prazo), com um worker próprio que verifica
e dispara esses lembretes. Postgres, Docker Compose e Bootstrap 5.

## Stack

- **Backend:** Django 6.1, Python 3.12
- **Banco:** PostgreSQL 16 (via Docker Compose); SQLite disponível para
  desenvolvimento rápido e para os testes automatizados
- **Front-end:** Bootstrap 5 (CDN) + Bootstrap Icons + FullCalendar.js;
  tipografia Inter (UI) + JetBrains Mono (datas/horários); paleta própria,
  mobile-first (nav em barra inferior de toque em telas pequenas)
- **Servidor de aplicação:** Gunicorn + WhiteNoise para estáticos
- **Worker de lembretes:** processo separado, **sem fila externa** —
  consulta o Postgres periodicamente (polling) via ORM do Django. Não usa
  Celery/Redis/RabbitMQ, só o mesmo banco que a aplicação já usa.
- **Autenticação:** sistema de usuário próprio (`accounts.User`) construído
  sobre `django.contrib.auth`. Senhas com hashing **Argon2**
  (`PASSWORD_HASHERS`), validadores de senha do Django ativos
- **Criptografia de dados em repouso:** campo `notes` das tarefas
  criptografado com **Fernet** (AES-128-CBC + HMAC) via `EncryptedTextField`
  customizado (`core/fields.py`) — nunca fica em texto plano no banco

## Funcionalidades

- Landing page pública
- Cadastro e login/logout (e-mail único, senha forte)
- Painel de tarefas com estatísticas (total, cumpridas, atrasadas, próximas)
- CRUD completo de tarefas, com proteção contra IDOR — um usuário nunca
  acessa/edita tarefa de outro (retorna 404)
- **Lembrete por tarefa:** ao criar/editar, marque "quero ser lembrado" e
  escolha a antecedência (10 min, 30 min, 1h, 3h, 1 dia ou 2 dias antes). O
  horário calculado (`Task.remind_at`) aparece no painel.
- Calendário mensal interativo (FullCalendar), alimentado por endpoint JSON
- Painel administrativo do Django (`/admin/`)

## O worker de lembretes

O comando `python manage.py send_reminders` (em `tasks/management/commands/`)
consulta as tarefas com lembrete pendente (`Task.objects.pending_reminders()`)
e as marca como notificadas (`Task.reminder_sent_at`).

```bash
python manage.py send_reminders                          # uma passada e sai
python manage.py send_reminders --loop                   # roda continuamente
python manage.py send_reminders --loop --interval 15      # a cada 15s
python manage.py send_reminders --loop --max-iterations 3 # limita passadas (uso em testes)
```

No Docker Compose ele roda como o serviço `worker`, contínuo, ao lado do
`web` — mesmo banco, sem infraestrutura extra.

> **Limitação deliberada, documentada aqui para não passar por trás do
> pano:** o worker identifica corretamente os lembretes vencidos e registra
> que foram "disparados", mas o disparo em si hoje é uma linha de log
> (stdout/`docker compose logs worker`) — **não envia e-mail, push ou SMS**.
> Ligar a um canal real de notificação é trocar uma função
> (`Command._notify` em `send_reminders.py`), mas exige credenciais de
> e-mail/push configuradas, o que ficou fora do escopo (rodar só com
> Postgres, sem outra infraestrutura).

## Rodando com Docker Compose (recomendado)

```bash
cp .env.example .env
# edite o .env: gere SECRET_KEY e FIELD_ENCRYPTION_KEY (comandos abaixo) e
# defina uma senha de banco forte

python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

docker compose up --build
```

Isso sobe três serviços:

| Serviço | Dockerfile | O que faz |
|---|---|---|
| `db` | imagem oficial `postgres:16-alpine` | banco de dados |
| `web` | `Dockerfile.web` | aplicação Django (Gunicorn), porta `8000` |
| `worker` | `Dockerfile.worker` | worker de lembretes, sem porta exposta |

`web` e `worker` são **imagens separadas** (Dockerfiles distintos), mesmo
compartilhando o código e as dependências — `worker` não carrega
Gunicorn/WhiteNoise nem roda `collectstatic`, já que não serve HTTP.

Para criar um superusuário para o `/admin/`:

```bash
docker compose exec web python manage.py createsuperuser
```

Para acompanhar os lembretes disparados pelo worker:

```bash
docker compose logs -f worker
```

Para parar:

```bash
docker compose down          # mantém os dados (volume postgres_data)
docker compose down -v       # remove também os dados do banco
```

## Rodando localmente sem Docker (desenvolvimento)

```bash
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements-dev.txt   # inclui requirements.txt + coverage

cp .env.example .env
# no .env, defina USE_SQLITE_FOR_TESTS=True para não precisar de Postgres local
# gere SECRET_KEY e FIELD_ENCRYPTION_KEY como mostrado acima

python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Em outro terminal, para rodar o worker localmente:

```bash
python manage.py send_reminders --loop
```

## Rotina de testes

```bash
./run_tests.sh              # django check + testes + relatório de cobertura + HTML
./run_tests.sh --no-cov     # só check + testes, sem medir cobertura (mais rápido)
```

A suíte tem **72 testes** (`accounts/tests.py`, `core/tests.py`,
`tasks/tests.py`) cobrindo models, forms, views, proteção contra IDOR e o
worker de lembretes (incluindo `--loop`, `--max-iterations` e interrupção
por `KeyboardInterrupt`).

**Cobertura: 100% das linhas** de todo o código de aplicação
(`accounts`, `core`, `tasks`, `rotina/urls.py`), medida com `coverage.py`
(config em `.coveragerc`). Ficam de fora, com justificativa documentada no
próprio `.coveragerc`:

- `*/migrations/*`, `manage.py`, `rotina/wsgi.py`, `rotina/asgi.py` —
  boilerplate gerado pelo Django, sem lógica de aplicação.
- `rotina/settings.py` — configuração declarativa por variável de
  ambiente; cobrir de forma significativa exigiria rodar a suíte inteira
  uma vez por combinação de env vars, o que não agrega confiança real.
- as 3 linhas do bloco `if settings.DEBUG:` em `rotina/urls.py` (serving de
  estáticos em dev sem proxy reverso) — o test runner do Django força
  `DEBUG=False` durante os testes, então esse bloco nunca executa em
  ambiente de teste; é o padrão recomendado pela própria documentação do
  Django, não lógica desta aplicação.

Para ver o relatório detalhado por arquivo depois de rodar:

```bash
open htmlcov/index.html    # macOS; no Linux: xdg-open htmlcov/index.html
```

Há também um workflow de CI (`.github/workflows/tests.yml`) que roda a
mesma rotina a cada push/PR e falha se a cobertura cair de 100%.

## Variáveis de ambiente (`.env`)

| Variável | Descrição |
|---|---|
| `DEBUG` | `True` em desenvolvimento, `False` em produção |
| `SECRET_KEY` | chave secreta do Django — gere uma nova, nunca reutilize a de exemplo |
| `ALLOWED_HOSTS` | hosts/domínios permitidos, separados por vírgula |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | credenciais do Postgres, usadas pelo container `db` e pelo Django |
| `POSTGRES_HOST` / `POSTGRES_PORT` | endereço do banco (`db`/`5432` dentro do Compose) |
| `FIELD_ENCRYPTION_KEY` | chave Fernet para criptografia de campos sensíveis — gere com o comando acima e **nunca a rotacione sem antes descriptografar os dados existentes com a chave antiga** |
| `USE_SQLITE_FOR_TESTS` | quando `True`, ignora Postgres e usa SQLite (dev local / testes / CI) |
| `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | ative (`True`) quando servir atrás de HTTPS em produção |

## Estrutura do projeto

```
rotina/
├── accounts/                    # usuário customizado, cadastro, login/logout
├── core/                         # landing page, criptografia (crypto.py, fields.py)
├── tasks/                         # model Task (com lembrete), painel, CRUD, calendário
│   └── management/commands/send_reminders.py   # worker de lembretes
├── templates/base.html
├── static/css/custom.css
├── Dockerfile.web                 # imagem do Django (Gunicorn)
├── Dockerfile.worker               # imagem do worker de lembretes
├── entrypoint.web.sh / entrypoint.worker.sh
├── docker-compose.yml              # db + web + worker
├── run_tests.sh                     # rotina de testes (check + testes + cobertura)
├── .github/workflows/tests.yml       # CI
├── requirements.txt / requirements-dev.txt
└── .env.example
```

## Notas de segurança

- Senhas: hashing Argon2, com PBKDF2 como fallback de compatibilidade.
- `Task.notes`: criptografado em repouso via Fernet, transparente na
  camada de model.
- CSRF, XSS (`SECURE_BROWSER_XSS_FILTER`, `X_FRAME_OPTIONS: DENY`),
  `SECURE_CONTENT_TYPE_NOSNIFF` habilitados por padrão; HSTS automático
  quando `DEBUG=False`.
- Ambos os containers (`web` e `worker`) rodam como usuário não-root.
- Toda query de `Task` é filtrada por `owner=request.user` nas views —
  protege contra IDOR.
- **Antes de subir para produção:** troque `SECRET_KEY`,
  `FIELD_ENCRYPTION_KEY` e a senha do Postgres pelos valores gerados para o
  seu ambiente.

## Validação realizada

Fluxo completo validado manualmente ponta a ponta: landing → cadastro
(hash Argon2) → login → criação de tarefa com lembrete → nota criptografada
em repouso confirmada via leitura direta da coluna no banco → painel →
calendário (página e JSON) → conclusão → edição → bloqueio de acesso de
outro usuário à mesma tarefa (404) → exclusão → `/admin/` → worker de
lembretes disparando, não duplicando disparo e ignorando tarefas concluídas/
sem lembrete/no futuro. Suíte automatizada com 72 testes, 100% de cobertura
de linha no código de aplicação.

Não foi possível executar `docker compose up` dentro deste sandbox (sem
Docker disponível) — revise o build dos dois Dockerfiles ao subir no seu
ambiente. O restante (Django/ORM/templates/views/worker) foi exercitado
diretamente, sem Docker.
