#!/bin/sh
set -e
python manage.py migrate --noinput
python manage.py popular_banco
exec gunicorn sistema_ponto.wsgi:application --bind 0.0.0.0:8000 --workers 2
