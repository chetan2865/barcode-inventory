release: python manage.py migrate --noinput --settings=config.settings_production
web: gunicorn config.wsgi:application --env DJANGO_SETTINGS_MODULE=config.settings_production --bind 0.0.0.0:$PORT --workers 3 --timeout 120 --access-logfile - --error-logfile -
