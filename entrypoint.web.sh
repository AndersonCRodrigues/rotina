#!/bin/sh
set -e

if [ "$USE_SQLITE_FOR_TESTS" != "True" ]; then
    echo "Aguardando o Postgres em ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
    while ! nc -z "${POSTGRES_HOST:-db}" "${POSTGRES_PORT:-5432}"; do
        sleep 0.5
    done
    echo "Postgres disponível."
fi

echo "Aplicando migrações..."
python manage.py migrate --noinput

echo "Coletando arquivos estáticos..."
python manage.py collectstatic --noinput

exec "$@"
