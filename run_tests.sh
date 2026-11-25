#!/bin/sh

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
