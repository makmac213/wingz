# syntax=docker/dockerfile:1
# ---------------------------------------------------------------------------
# Wingz Ride Management API — demo container image
# ---------------------------------------------------------------------------
FROM python:3.12-slim

# Keep Python lean and predictable inside the container.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# System dependencies. build-essential covers any C-extension builds
# (e.g. fallback compilation paths); libpq-dev supports psycopg2.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first to maximise Docker layer caching.
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy the rest of the project.
COPY . .

# Collect static files. Harmless if there are none — avoids runtime warnings.
RUN python manage.py collectstatic --noinput

# Entrypoint runs migrations + seed data on every fresh container start.
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["gunicorn", "wingz.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--timeout", "60"]
