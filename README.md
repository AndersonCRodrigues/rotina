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
- Página de métricas com quatro indicadores por perfil, filtro de período,
  gráfico diário e exportação CSV

O calendário, o painel e os formulários web exibem os horários de
`America/Sao_Paulo` mesmo em navegadores configurados para outro fuso.
Ao editar outros campos de uma tarefa, o formulário preserva os segundos
e microssegundos já gravados se o horário exibido continuar igual.
Se os eventos falharem ao carregar, é possível tentar novamente no
calendário sem perder o período selecionado. No formulário, o campo de
antecedência fica disponível ao ativar o lembrete.

## Dashboards de métricas

Usuários comuns acessam **Métricas** em `/tarefas/metricas/` e mantêm o
acesso ao painel de tarefas e ao calendário. A página mostra total de
tarefas próprias, concluídas, atrasadas e próximas, com base na data
agendada. O gráfico mostra as tarefas agendadas por dia.

![Dashboard do usuário comum com filtro, quatro indicadores e gráfico de tarefas agendadas](.github/assets/metricas-usuario.png)

O superadmin abre diretamente as métricas do sistema ao entrar. Na
interface autenticada, o perfil tem acesso ao dashboard, ao CSV e à saída.
Os indicadores globais são contas cadastradas, contas distintas que
criaram tarefas, tarefas criadas e tarefas concluídas. Cada indicador usa
a data do respectivo evento. O gráfico mostra as tarefas criadas por dia.

![Dashboard do superadmin com filtro, quatro indicadores globais e gráfico de tarefas criadas](.github/assets/metricas-superadmin.png)

O filtro usa `inicio` e `fim` no formato `AAAA-MM-DD`. As duas datas são
inclusivas, no fuso `America/Sao_Paulo`. O período inicial contém os
últimos 30 dias, incluindo hoje. Um período explícito exige as duas datas
em ordem e pode conter até 366 dias. Acima de 31 dias, o gráfico agrupa
dias consecutivos para manter a leitura. O CSV inclui cada dia do período e
uma linha de totais. No relatório global, a contagem de contas que
criaram tarefas no período elimina repetições entre dias.

Web, API e CSV usam as mesmas agregações. São feitas uma consulta para
os dados do usuário comum e quatro para os dados globais, além da
autenticação. A quantidade de consultas independe do número de registros.

## API REST — Django REST Framework

A API utiliza o modelo de tarefas, o banco de dados e a validação de usuário e senha do Django existentes. Para os endpoints `/api/`, a autenticação é feita **exclusivamente pelo TokenAuthentication nativo do DRF**: não há JWT, cookies de sessão ou CSRF na autenticação da API. A interface web mantém o login/logout por sessão em `/contas/` e continua funcionando normalmente.

Cada token identifica um `accounts.User`. Em todas as rotas de tarefas, o servidor filtra os registros por `owner=request.user`. Um usuário não consegue listar, consultar, alterar, concluir ou excluir tarefas de outro usuário, mesmo sabendo o ID. O campo `owner` não pode ser escolhido no JSON.

**URL base em desenvolvimento:** `http://localhost:8000`.

### Endpoints

| Método | Rota | Operação | Sucesso |
|---|---|---|---|
| POST | `/api/cadastro/` | Criar conta comum com `username`, `email`, `password1` e `password2` | 201 |
| POST | `/api/login/` | Validar `username` e `password` e obter token DRF | 200 |
| POST | `/api/logout/` | Revogar o token enviado no header | 204 |
| GET | `/api/me/` | Dados da conta autenticada | 200 |
| GET | `/api/metricas/` | Retornar indicadores e série diária conforme o perfil | 200 |
| GET | `/api/metricas/csv/` | Baixar os indicadores e a série diária em CSV | 200 |
| GET | `/api/tarefas/` | Listar apenas as próprias tarefas | 200 |
| POST | `/api/tarefas/` | Criar tarefa para a conta autenticada | 201 |
| GET | `/api/tarefas/resumo/` | Contar tarefas próprias por situação | 200 |
| GET | `/api/tarefas/calendario/eventos.json` | Listar eventos do calendário próprio | 200 |
| GET | `/api/tarefas/{id}/` | Detalhar tarefa própria | 200 |
| PUT | `/api/tarefas/{id}/` | Atualizar campos editáveis integralmente | 200 |
| PATCH | `/api/tarefas/{id}/` | Atualizar apenas os campos enviados | 200 |
| DELETE | `/api/tarefas/{id}/` | Excluir tarefa própria | 204 |
| POST | `/api/tarefas/{id}/concluir/` | Concluir tarefa própria | 200 |

Os endpoints protegidos exigem `Authorization: Token <token>`. Cadastro e
login são públicos. O cadastro aplica as mesmas validações da interface web
e retorna `id`, `username` e `email`. Faça login para obter o token. O logout
revoga o token atual, que é armazenado no banco e permanece válido até ser
revogado. Use **HTTPS em produção**.

O resumo retorna `total`, `done`, `overdue` e `upcoming`. O calendário
retorna uma lista de eventos com `id`, `title`, `start`, `color` e `url`.
O campo `start` segue ISO 8601, e `url` aponta para o detalhe da tarefa na API.
O feed web e o da API aceitam `start` e `end` em ISO 8601. O início é
inclusivo e o fim é exclusivo. Envie os dois parâmetros juntos. O
calendário web usa o período visível e chamadas sem os parâmetros
retornam todos os eventos da conta.
Os endpoints de métricas aceitam o filtro `?inicio=2026-11-01&fim=2026-11-30`.
Um período inválido retorna `400 Bad Request`. O JSON de métricas inclui
`inicio`, `fim`, `labels`, `totals` e `daily`.

### Testar com Insomnia, Thunder Client ou cliente REST

Crie uma coleção **Rotina API** e configure `base_url = http://localhost:8000` como variável do cliente, se disponível. Em requisições com JSON, use `Content-Type: application/json` e `Accept: application/json`.

#### 1. Fazer login e obter token

Selecione método **POST**, URL `{{base_url}}/api/login/`, tipo de body **JSON**, sem autenticação (**No Auth**):

```json
{
  "username": "usuario_teste",
  "password": "senha_da_conta"
}
```

Resposta de exemplo (`200 OK`):

```json
{
  "token": "TOKEN_RETORNADO_PELO_SERVIDOR"
}
```

O token acima é ilustrativo. A conta precisa existir previamente; pode ser criada no cadastro web `/contas/cadastro/` ou pelo Django Admin. Credenciais inválidas retornam `400 Bad Request`. Tentativas excessivas de login podem receber `429 Too Many Requests`.

#### 2. Configurar autenticação nas demais requisições

Em **Headers**, inclua:

| Header | Valor |
|---|---|
| `Authorization` | `Token TOKEN_RETORNADO_PELO_SERVIDOR` |
| `Accept` | `application/json` |
| `Content-Type` | `application/json` (em POST, PUT e PATCH com body JSON) |

Em clientes com opção de API Key, configure o header `Authorization` manualmente com o prefixo `Token` e um espaço. **Não selecione Bearer Token** (esse modo normalmente usa `Bearer`, incompatível com o prefixo padrão do DRF). Não é necessário enviar `sessionid`, `csrftoken` ou `X-CSRFToken`.

#### 3. Consultar a própria conta

Método **GET**, URL `{{base_url}}/api/me/`, sem body, com o header `Authorization`.

Exemplo de resposta (`200 OK`):

```json
{
  "id": 1,
  "username": "usuario_teste",
  "email": "usuario@exemplo.com"
}
```

A API usa o usuário vinculado ao token. Não recebe ID de usuário como parâmetro.

#### 4. Listar e filtrar tarefas

Método **GET**, URL `{{base_url}}/api/tarefas/`, sem body, com token.

Em **Query/Params**, é possível combinar:

| Parâmetro | Exemplo | Resultado |
|---|---|---|
| `status` | `todo` | Filtra `todo`, `in_progress` ou `done` |
| `search` | `estudar` | Busca no título |
| `ordering` | `scheduled_for` | Menor agendamento primeiro |
| `ordering` | `-scheduled_for` | Maior agendamento primeiro |
| `ordering` | `-created_at` | Mais recentes primeiro |

Exemplo: `{{base_url}}/api/tarefas/?status=todo&search=estudar&ordering=scheduled_for`. A lista contém somente tarefas pertencentes ao usuário identificado pelo token. A busca não consulta as notas porque elas são criptografadas no banco.

#### 5. Criar uma tarefa

Método **POST**, URL `{{base_url}}/api/tarefas/`, com token, body **JSON**:

```json
{
  "title": "Estudar Django REST Framework",
  "notes": "Revisar serializers e permissões",
  "scheduled_for": "2026-12-01T18:00:00-03:00",
  "status": "todo",
  "remind_enabled": true,
  "remind_minutes_before": 30
}
```

Resposta esperada: `201 Created`, com o ID criado e os dados da tarefa, por exemplo:

```json
{
  "id": 1,
  "title": "Estudar Django REST Framework",
  "notes": "Revisar serializers e permissões",
  "status": "todo",
  "scheduled_for": "2026-12-01T18:00:00-03:00",
  "remind_enabled": true,
  "remind_minutes_before": 30,
  "completed_at": null,
  "remind_at": "2026-12-01T17:30:00-03:00",
  "is_overdue": false,
  "created_at": "2026-11-10T12:00:00-03:00",
  "updated_at": "2026-11-10T12:00:00-03:00"
}
```

Os valores de ID, horários e datas dependem do banco e do momento da operação. `title` (máximo 200 caracteres) e `scheduled_for` (ISO 8601) são obrigatórios na criação. `status` aceita `todo`, `in_progress`, `done`; o padrão é `todo`. Para lembretes habilitados, `remind_minutes_before` deve ser `10`, `30`, `60`, `180`, `1440` ou `2880`. `notes` é opcional e criptografado em repouso.

`id`, `completed_at`, `remind_at`, `is_overdue`, `created_at` e `updated_at` são campos de leitura. O campo `owner` é definido pelo servidor, e `reminder_sent_at` não é exposto.

#### 6. Consultar ou atualizar uma tarefa

Para consultar: **GET** `{{base_url}}/api/tarefas/1/`, sem body.

Para alterar parcialmente: **PATCH** `{{base_url}}/api/tarefas/1/`, com token e body JSON:

```json
{
  "title": "Revisar autenticação DRF",
  "status": "in_progress"
}
```

Para atualizar totalmente: **PUT** na mesma URL, enviando os campos obrigatórios e demais valores desejados, por exemplo:

```json
{
  "title": "Revisar API de tarefas",
  "notes": "Validar métodos e permissões",
  "scheduled_for": "2026-12-02T15:00:00-03:00",
  "status": "in_progress",
  "remind_enabled": false
}
```

GET, PUT e PATCH de tarefas próprias retornam `200 OK`. IDs de outro usuário ou inexistentes retornam `404 Not Found`.

Ao desativar um lembrete, a antecedência é apagada. Ao reagendar ou modificar o lembrete, o envio anterior é reiniciado. Quando o status passa para `done`, `completed_at` é registrado; quando a tarefa é reaberta, é apagado. O worker registra lembretes no log, mas não envia SMS, push ou e-mail.

#### 7. Concluir e excluir

Para concluir: **POST** `{{base_url}}/api/tarefas/1/concluir/`, com token e sem body. Sucesso: `200 OK`, tarefa com `status: "done"` e `completed_at` preenchido.
Repetir a conclusão de uma tarefa já concluída preserva `completed_at` e
`updated_at`.

Para excluir: **DELETE** `{{base_url}}/api/tarefas/1/`, com token e sem body. Sucesso: `204 No Content`.

#### 8. Revogar o token (logout)

Método **POST**, URL `{{base_url}}/api/logout/`, com `Authorization: Token <token_atual>`, sem body. Sucesso: `204 No Content`, e o token deixa de funcionar imediatamente. Um novo login cria outro token.

### Respostas de erro

| HTTP | Situação |
|---|---|
| 400 | Credenciais inválidas no login ou campos inválidos na tarefa |
| 401 | Token ausente, revogado ou incorreto em rota protegida |
| 404 | Tarefa inexistente ou pertencente a outro usuário |
| 405 | Método HTTP incorreto |
| 429 | Muitas tentativas de login no intervalo configurado |

### Preparar a aplicação e executar testes

O DRF utiliza `rest_framework.authtoken`, que inclui sua própria tabela e migrations. **Execute `migrate` após atualizar o código**, inclusive nos ambientes que já têm usuários cadastrados:

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test tasks.test_api
python manage.py test
```

No Docker Compose, com os serviços no ar:

```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test tasks.test_api
docker compose exec web python manage.py test
```

Para testar localmente sem o PostgreSQL, defina `USE_SQLITE_FOR_TESTS=True` no ambiente antes dos comandos de teste. O host `db` só funciona na rede do Docker Compose; use `localhost` com porta exposta para conexões locais a PostgreSQL.

Se a `SECRET_KEY` incluir `$` no `.env`, coloque o valor entre aspas simples para não ser interpretado pelo Docker Compose. Nunca publique chaves e senhas reais. Não altere `FIELD_ENCRYPTION_KEY` em bancos com notas criptografadas sem planejar a migração.

Os testes automatizados da API e de autenticação estão em `tasks/test_api.py`.

## O worker de lembretes

O comando `python manage.py send_reminders` (em `tasks/management/commands/`)
consulta as tarefas com lembrete pendente (`Task.objects.pending_reminders()`)
e as marca como notificadas (`Task.reminder_sent_at`).
Quando duas execuções encontram a mesma tarefa, apenas uma registra o
lembrete. Se a tarefa for reagendada antes da reserva, o worker descarta
o horário anterior e reavalia a nova configuração na próxima verificação.

```bash
python manage.py send_reminders
python manage.py send_reminders --loop
python manage.py send_reminders --loop --interval 15
python manage.py send_reminders --loop --max-iterations 3
```

O comando padrão faz uma verificação. Com `--loop`, ele roda continuamente.
Use `--interval` para ajustar o intervalo em segundos e
`--max-iterations` para limitar o número de verificações em testes.

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
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Defina no `.env` as duas chaves geradas e uma senha para o banco. Depois inicie o Compose.

```bash
docker compose up --build
```

Para criar o superadmin automaticamente, preencha `SUPERADMIN_EMAIL` e
`SUPERADMIN_PASSWORD` no `.env` antes de iniciar o serviço `web`. O serviço
executa `python manage.py bootstrap_superadmin` após as migrações. O e-mail
em minúsculas também é o nome de usuário da conta criada. A senha segue os
validadores do Django. Reiniciar o serviço preserva a conta e sua senha.
Com ambas as variáveis vazias, a criação automática é desativada.

Isso sobe três serviços:

| Serviço | Dockerfile | O que faz |
|---|---|---|
| `db` | imagem oficial `postgres:16-alpine` | banco de dados |
| `web` | `Dockerfile.web` | aplicação Django (Gunicorn), porta `8000` |
| `worker` | `Dockerfile.worker` | worker de lembretes, sem porta exposta |

`web` e `worker` são **imagens separadas** (Dockerfiles distintos), mesmo
compartilhando o código e as dependências — `worker` não carrega
Gunicorn/WhiteNoise nem roda `collectstatic`, já que não serve HTTP.
O serviço `web` aplica as migrações antes de iniciar o Gunicorn. O Compose
inicia o `worker` depois que a porta interna do `web` estiver disponível
e encaminha os sinais de encerramento ao processo do worker.

Para acompanhar os lembretes disparados pelo worker:

```bash
docker compose logs -f worker
```

Para parar e manter os dados do PostgreSQL:

```bash
docker compose down
```

Use `docker compose down -v` quando também quiser remover o volume do banco.

## Rodando localmente sem Docker (desenvolvimento)

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt

cp .env.example .env
```

No Windows, ative o ambiente virtual com `venv\Scripts\activate`.

Configure um PostgreSQL acessível no `.env` e preencha as chaves e credenciais
descritas acima. Reserve `USE_SQLITE_FOR_TESTS=True` para testes, pois cada
processo abre um banco SQLite em memória. Em seguida, execute:

```bash
python manage.py migrate
python manage.py bootstrap_superadmin
python manage.py runserver
```

Em outro terminal, para rodar o worker localmente:

```bash
python manage.py send_reminders --loop
```

## Rotina de testes

```bash
./run_tests.sh
./run_tests.sh --no-cov
```

O primeiro comando executa a verificação do Django e gera os relatórios de
cobertura. Com `--no-cov`, o script executa a verificação e os testes.

A suíte possui **133 testes**, incluindo autenticação, criação inicial do
superadmin, API, métricas, isolamento de tarefas por usuário e worker de lembretes.

**Cobertura verificada: 100% das linhas** de todo o código de aplicação
(`accounts`, `core`, `tasks`, `rotina/urls.py`), medida com `coverage.py`
(configuração em `.coveragerc`). A medição exclui os arquivos de testes,
as migrações, os pontos de entrada e as configurações do Django.

Para ver o relatório detalhado por arquivo depois de rodar:

```bash
open htmlcov/index.html
```

No Linux, use `xdg-open htmlcov/index.html`.

Há também um workflow de CI (`.github/workflows/tests.yml`) que roda a
mesma rotina a cada push/PR e falha se a cobertura cair de 100%.

## Variáveis de ambiente (`.env`)

| Variável | Descrição |
|---|---|
| `DEBUG` | `True` em desenvolvimento, `False` em produção |
| `SECRET_KEY` | chave secreta do Django — gere uma nova, nunca reutilize a de exemplo |
| `ALLOWED_HOSTS` | hosts/domínios permitidos, separados por vírgula |
| `SUPERADMIN_EMAIL` / `SUPERADMIN_PASSWORD` | credenciais para a criação inicial do superadmin |
| `POSTGRES_DB` / `POSTGRES_USER` / `POSTGRES_PASSWORD` | credenciais do Postgres, usadas pelo container `db` e pelo Django |
| `POSTGRES_HOST` / `POSTGRES_PORT` | endereço do banco (`db`/`5432` dentro do Compose) |
| `FIELD_ENCRYPTION_KEY` | chave Fernet para criptografia de campos sensíveis — gere com o comando acima e **nunca a rotacione sem antes descriptografar os dados existentes com a chave antiga** |
| `USE_SQLITE_FOR_TESTS` | quando `True`, ignora Postgres e usa SQLite (dev local / testes / CI) |
| `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | ative (`True`) quando servir atrás de HTTPS em produção |

## Estrutura do projeto

```
rotina/
├── accounts/
├── core/
├── tasks/
│   └── management/commands/send_reminders.py
├── templates/base.html
├── static/css/custom.css
├── Dockerfile.web
├── Dockerfile.worker
├── entrypoint.web.sh / entrypoint.worker.sh
├── docker-compose.yml
├── run_tests.sh
├── .github/workflows/tests.yml
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
- As consultas de tarefas individuais e métricas pessoais usam
  `owner=request.user`. As métricas globais exigem uma conta superadmin.
- **Antes de subir para produção:** troque `SECRET_KEY`,
  `FIELD_ENCRYPTION_KEY` e a senha do Postgres pelos valores gerados para o
  seu ambiente.

## Validação realizada

Validação ponta a ponta com Docker Compose, PostgreSQL 16 e `DEBUG=False`.
Foram verificados os fluxos web e API, a criação inicial do superadmin,
os dashboards por perfil, o CSV filtrado, as notas criptografadas no
banco e o registro do lembrete pelo worker.
