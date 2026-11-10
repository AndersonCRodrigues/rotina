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

## API REST — Django REST Framework

A API utiliza os mesmos modelos, banco e usuários da aplicação web. A autenticação é
feita por **sessão do Django**, usando `accounts.User`, sem JWT ou autenticação
paralela. O acesso exige login; cada usuário só consegue consultar e modificar
suas próprias tarefas. As notas (`notes`) continuam criptografadas no banco.

**Endereço base:** `http://localhost:8000` (ao executar o servidor local ou o Docker Compose).

### Rotas da API

| Método HTTP | Endpoint | Uso | Resposta de sucesso |
|---|---|---|---|
| GET | `/api/me/` | Dados do usuário autenticado | 200 |
| GET | `/api/tarefas/` | Listar tarefas do usuário | 200 |
| POST | `/api/tarefas/` | Cadastrar tarefa | 201 |
| GET | `/api/tarefas/{id}/` | Consultar uma tarefa | 200 |
| PUT | `/api/tarefas/{id}/` | Substituir os campos editáveis | 200 |
| PATCH | `/api/tarefas/{id}/` | Atualizar campos específicos | 200 |
| DELETE | `/api/tarefas/{id}/` | Excluir tarefa | 204 |
| POST | `/api/tarefas/{id}/concluir/` | Marcar tarefa como concluída | 200 |

`{id}` representa o identificador de uma tarefa pertencente ao usuário autenticado.

Rotas de autenticação existentes: `/contas/cadastro/`, `/contas/login/` e
`/contas/logout/` (o logout usa POST). A interface navegável do DRF também
possui `/api-auth/login/` e `/api-auth/logout/`. Os endpoints originais do
painel, do calendário e do admin continuam funcionando.

### Campos aceitos para criar e atualizar tarefas

| Campo | Tipo | Regra |
|---|---|---|
| `title` | texto | Obrigatório na criação; até 200 caracteres |
| `scheduled_for` | data/hora ISO 8601 | Obrigatório na criação, com fuso horário recomendado |
| `notes` | texto | Opcional, criptografado em repouso |
| `status` | texto | `todo`, `in_progress` ou `done`; padrão `todo` |
| `remind_enabled` | booleano | Habilita/desabilita o lembrete; padrão `false` |
| `remind_minutes_before` | número inteiro ou `null` | `10`, `30`, `60`, `180`, `1440` ou `2880`; obrigatório se o lembrete estiver ativo |

Campos devolvidos como somente leitura: `id`, `completed_at`, `remind_at`,
`is_overdue`, `created_at`, `updated_at`. O proprietário (`owner`) é
atribuído automaticamente a partir da sessão, não podendo ser escolhido na
requisição. O campo interno `reminder_sent_at` não é exposto.

Ao desativar o lembrete, a antecedência é apagada. Ao reagendar uma tarefa ou
modificar seu lembrete, o registro de envio anterior é reiniciado para
permitir o novo disparo. O worker atual registra os lembretes em log; ele não
envia notificações por e-mail, push ou SMS.

### Testar pelo Insomnia, Thunder Client ou outro cliente REST

As requisições abaixo podem ser montadas diretamente no **Insomnia**, no **Thunder Client (VS Code)** ou em um cliente REST semelhante. Não é necessário utilizar terminal para fazer requisições HTTP.

Crie uma coleção chamada **Rotina API** e configure uma variável de ambiente:

| Variável | Valor para execução local |
|---|---|
| `base_url` | `http://localhost:8000` |

Em cada requisição, utilize `{{base_url}}` antes do caminho da rota. Substitua `{id}` pelo ID retornado ao cadastrar uma tarefa. Se o cliente não oferecer variáveis, utilize a URL completa, como `http://localhost:8000/api/tarefas/`.

#### 1. Autenticação por sessão Django

A API **não usa Bearer Token, JWT nem Basic Auth**. Em **Auth**, selecione **No Auth**: o acesso será reconhecido pelos cookies `sessionid` e `csrftoken` gerados pelo Django após o login.

1. Crie uma requisição `GET {{base_url}}/contas/login/` e envie-a. O Django disponibiliza o formulário de login e um cookie `csrftoken`. Copie o token CSRF do cookie ou do campo oculto `csrfmiddlewaretoken` do formulário.
2. Crie uma requisição `POST {{base_url}}/contas/login/`. Em **Body**, escolha **Form URL Encoded** (`application/x-www-form-urlencoded`) e preencha os campos:

   | Campo | Exemplo |
   |---|---|
   | `username` | `usuario_teste` |
   | `password` | `senha_da_conta` |
   | `csrfmiddlewaretoken` | token obtido no passo anterior |

3. O cliente deve manter os cookies recebidos pelo mesmo host. Se ele não conservar cookies automaticamente, configure seu gerenciador de cookies para persistir `csrftoken` e `sessionid` entre as requisições. Um login válido normalmente retorna `302 Found` para o painel (ou a página de destino `200` caso o cliente acompanhe o redirecionamento). Um `200` no próprio formulário de login pode indicar credenciais ou dados inválidos.
4. Após o login, o Django pode renovar o token CSRF. Utilize o valor **atual** do cookie `csrftoken` nas operações de escrita, no header `X-CSRFToken`. Para consultar os dados da sessão, envie `GET {{base_url}}/api/me/`.

Não é necessário colocar usuário e senha nas requisições da API após o login: o `sessionid` identifica a sessão. Para `GET`, basta o cookie da sessão; para `POST`, `PUT`, `PATCH` e `DELETE`, envie também o header `X-CSRFToken`. Preserve o cookie no cliente REST e não desative a verificação CSRF.

**Headers para requisições com JSON:**

| Header | Valor |
|---|---|
| `Content-Type` | `application/json` |
| `Accept` | `application/json` |
| `X-CSRFToken` | token atual do cookie `csrftoken`, nos métodos que alteram dados |

Os cookies de sessão são administrados no gerenciador de cookies do cliente. O header `X-CSRFToken` não é necessário para `GET`.

#### 2. Consultar o usuário autenticado

| Campo | Valor |
|---|---|
| Método | `GET` |
| URL | `{{base_url}}/api/me/` |
| Body | Nenhum |
| Sucesso | `200 OK` |

Resposta ilustrativa:

```json
{
  "id": 1,
  "username": "usuario_teste",
  "email": "usuario@exemplo.com"
}
```

#### 3. Listar, pesquisar e filtrar tarefas

| Campo | Valor |
|---|---|
| Método | `GET` |
| URL | `{{base_url}}/api/tarefas/` |
| Body | Nenhum |
| Sucesso | `200 OK` |

Na aba **Query**/**Params** do cliente, adicione os parâmetros opcionais:

| Parâmetro | Exemplo | Função |
|---|---|---|
| `status` | `todo` | Filtrar tarefas a fazer (`todo`, `in_progress`, `done`) |
| `search` | `estudar` | Pesquisar título, sem diferenciar maiúsculas de minúsculas |
| `ordering` | `scheduled_for` | Ordenar pela data de agendamento crescente |
| `ordering` | `-scheduled_for` | Ordenar pela data de agendamento decrescente |
| `ordering` | `-created_at` | Mostrar primeiro as tarefas mais recentes |

Exemplo de URL com filtros combinados: `{{base_url}}/api/tarefas/?status=todo&search=estudar&ordering=scheduled_for`.

A pesquisa não procura no campo `notes`, porque ele é criptografado no banco.

#### 4. Criar uma tarefa

| Campo | Valor |
|---|---|
| Método | `POST` |
| URL | `{{base_url}}/api/tarefas/` |
| Body | **JSON** |
| Headers | `Content-Type: application/json` e `X-CSRFToken` |
| Sucesso | `201 Created` |

Em **Body → JSON**, informe:

```json
{
  "title": "Estudar DRF",
  "notes": "Revisar serializers",
  "scheduled_for": "2026-12-01T18:00:00-03:00",
  "status": "todo",
  "remind_enabled": true,
  "remind_minutes_before": 30
}
```

Exemplo ilustrativo de resposta (os IDs e horários variam conforme o banco e o momento da criação):

```json
{
  "id": 1,
  "title": "Estudar DRF",
  "notes": "Revisar serializers",
  "status": "todo",
  "scheduled_for": "2026-12-01T18:00:00-03:00",
  "remind_enabled": true,
  "remind_minutes_before": 30,
  "completed_at": null,
  "remind_at": "2026-12-01T17:30:00-03:00",
  "is_overdue": false,
  "created_at": "2026-11-09T12:00:00-03:00",
  "updated_at": "2026-11-09T12:00:00-03:00"
}
```

#### 5. Consultar uma tarefa específica

| Campo | Valor |
|---|---|
| Método | `GET` |
| URL | `{{base_url}}/api/tarefas/1/` |
| Body | Nenhum |
| Sucesso | `200 OK` |

A resposta contém os campos da tarefa. IDs inexistentes ou pertencentes a outro usuário retornam `404 Not Found`.

#### 6. Atualizar uma tarefa parcialmente

| Campo | Valor |
|---|---|
| Método | `PATCH` |
| URL | `{{base_url}}/api/tarefas/1/` |
| Body | **JSON** |
| Headers | `Content-Type: application/json` e `X-CSRFToken` |
| Sucesso | `200 OK` |

```json
{
  "title": "Estudar DRF e autenticação",
  "status": "in_progress"
}
```

O método `PATCH` modifica somente os campos enviados. O método `PUT` utiliza a mesma rota, mas exige os campos obrigatórios para uma atualização completa. Exemplo de **Body → JSON** para `PUT`:

```json
{
  "title": "Revisar API REST",
  "notes": "Conferir todos os endpoints",
  "scheduled_for": "2026-12-02T15:00:00-03:00",
  "status": "in_progress",
  "remind_enabled": false
}
```

Quando `remind_enabled` for `false`, `remind_minutes_before` será definido como `null`. Se uma tarefa for reagendada ou suas configurações de lembrete forem alteradas, o registro de envio anterior será reiniciado.

#### 7. Concluir uma tarefa

| Campo | Valor |
|---|---|
| Método | `POST` |
| URL | `{{base_url}}/api/tarefas/1/concluir/` |
| Body | Nenhum |
| Header | `X-CSRFToken` |
| Sucesso | `200 OK` |

A tarefa passa para `status: "done"` e recebe `completed_at`. A resposta contém os dados atualizados.

#### 8. Excluir uma tarefa

| Campo | Valor |
|---|---|
| Método | `DELETE` |
| URL | `{{base_url}}/api/tarefas/1/` |
| Body | Nenhum |
| Header | `X-CSRFToken` |
| Sucesso | `204 No Content` |

A exclusão não devolve JSON. Confirme que o identificador corresponde à tarefa que deseja remover.

### Erros e testes

| HTTP | Significado |
|---|---|
| 400 | Dados incorretos, campo obrigatório ausente ou regra de lembrete violada |
| 403 | Sessão ausente ou token CSRF inválido em operações de escrita |
| 404 | Tarefa inexistente ou pertencente a outro usuário |
| 405 | Método HTTP não permitido na rota |

Para testar sem PostgreSQL no Linux:

```bash
export USE_SQLITE_FOR_TESTS=True
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test tasks.test_api
python manage.py test
bash run_tests.sh
```

O host PostgreSQL `db` só é resolvido dentro da rede do Docker Compose. Para
executar os testes no container, use
`docker compose exec web python manage.py test tasks.test_api`.

Se a `SECRET_KEY` do arquivo `.env` contiver `$`, coloque o valor entre aspas
simples para impedir a interpolação pelo Docker Compose. Não divulgue chaves
reais e não altere `FIELD_ENCRYPTION_KEY` de bancos com notas criptografadas
sem planejar a migração das informações.

A inclusão do DRF acrescentou testes em `tasks/test_api.py`; o índice de 100%
de cobertura registrado anteriormente diz respeito à versão sem a API e
precisa ser medido novamente.

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

A suíte original possui **72 testes** (`accounts/tests.py`, `core/tests.py`,
`tasks/tests.py`) cobrindo models, forms, views, proteção contra IDOR e o
worker de lembretes (incluindo `--loop`, `--max-iterations` e interrupção
por `KeyboardInterrupt`).

**Cobertura original: 100% das linhas** de todo o código de aplicação
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

- Senhas: hashing Argon2, com PBKDG2 como fallback de compatibilidade.
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
sem lembrete/no futuro. A suíte original possui 72 testes e registrava 100% de cobertura; a integração DRF acrescenta testes e exige nova medição.

Não foi possível executar `docker compose up` dentro deste sandbox (sem
Docker disponível) — revise o build dos dois Dockerfiles ao subir no seu
ambiente. O restante (Django/ORM/templates/views/worker) foi exercitado
diretamente, sem Docker.
