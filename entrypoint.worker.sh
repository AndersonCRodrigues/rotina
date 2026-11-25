#!/bin/sh
set -e

if [ "$USE_SQLITE_FOR_TESTS" != "True" ]; then
    echo "[worker] Aguardando o Postgres em ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
    while ! nc -z "${POSTGRES_HOST:-db}" "${POSTGRES_PORT:-5432}"; do
        sleep 0.5
    done
    echo "[worker] Postgres disponível."
fi

echo "[worker] Aplicando migrações..."
python manage.py migrate --noinput

exec "$@"
