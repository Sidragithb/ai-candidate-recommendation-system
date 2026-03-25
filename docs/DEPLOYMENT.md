# Production Deployment Guide

## Stack

Production should run with:

- Django served by Gunicorn
- Nginx as reverse proxy
- PostgreSQL for relational data
- Redis for Celery and cache
- Qdrant for semantic search
- Celery worker for background parsing/indexing

## Required Environment

```env
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=your-domain.com,.your-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com
DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_SESSION_COOKIE_SECURE=true
DJANGO_CSRF_COOKIE_SECURE=true
DJANGO_USE_X_FORWARDED_PROTO=true

DJANGO_DB_ENGINE=postgres
DJANGO_DB_NAME=candidate_ai
DJANGO_DB_USER=postgres
DJANGO_DB_PASSWORD=change-me
DJANGO_DB_HOST=postgres
DJANGO_DB_PORT=5432

REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

QDRANT_URL=http://qdrant:6333
QDRANT_COLLECTION=candidate_embeddings
```

## Services

`docker-compose.yml` includes:

- `web`: Django + Gunicorn
- `celery`: background worker
- `nginx`: static/media + reverse proxy
- `postgres`: relational database
- `redis`: cache and broker
- `qdrant`: vector database

## Deploy

```powershell
docker compose up --build
```

Entrypoint behavior:

- runs migrations
- collects static files
- starts the requested process

## Checklist

1. Set secure Django env vars.
2. Point app to PostgreSQL, Redis, and Qdrant.
3. Configure embedding/parser providers.
4. Run `docker compose up --build`.
5. Verify `GET /api/health/`.
6. Create a job and confirm embedding gets generated.
7. Upload single and bulk resumes and confirm Celery processes them.
8. Test `POST /api/chatbot/search/` for hybrid/explainable ranking.

## Notes

- Do not use `runserver` in production.
- Redis is required for background processing and search caching.
- If OpenAI is not configured, the app falls back to heuristic parsing and placeholder embeddings.
