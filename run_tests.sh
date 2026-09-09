#!/bin/sh
# Rotina de testes do projeto Rotina.
#
# Uso:
#   ./run_tests.sh            # roda tudo (check + testes + cobertura)
#   ./run_tests.sh --no-cov   # roda check + testes, sem medir cobertura
#
# Pressupõe um ambiente com as dependências de requirements.txt instaladas
# (veja o README) e USE_SQLITE_FOR_TESTS=True no .env, para não depender de
# um Postgres real só para rodar a suíte.

set -e

echo "==> django check"
python manage.py check

if [ "$1" = "--no-cov" ]; then
    echo "==> manage.py test"
    python manage.py test
    exit 0
fi

echo "==> coverage run"
coverage run manage.py test

echo "==> coverage report"
coverage report -m

echo "==> coverage html (htmlcov/index.html)"
coverage html
