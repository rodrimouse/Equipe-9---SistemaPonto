#!/bin/sh
set -e
python manage.py migrate --noinput
python manage.py popular_banco
if [ "$#" -gt 0 ]; then
  exec "$@"
fi
exec gunicorn sistema_ponto.wsgi:application --bind 0.0.0.0:8000 --workers 2
