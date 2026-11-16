FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# Les fichiers statiques sont préparés une fois pour toutes dans l'image.
RUN DJANGO_DEBUG=false DJANGO_SECRET_KEY=collectstatic-seulement python manage.py collectstatic --noinput

RUN useradd --system --uid 1001 app && chown -R app /app
USER app

EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && gunicorn config.wsgi --bind 0.0.0.0:8000 --workers 3"]
