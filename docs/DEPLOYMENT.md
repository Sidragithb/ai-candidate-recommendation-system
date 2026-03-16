# Production Deployment Guide

## Goal

This project can run locally with Django's development server, but production deployment should use:

- a real web server
- PostgreSQL
- Qdrant
- Ollama or OpenAI embeddings
- HTTPS-aware Django settings

## Required Services

- Django application server
- PostgreSQL database
- Qdrant vector database
- Ollama service if using local embeddings
- ngrok is only for local webhook testing, not production

## Recommended Environment Settings

```env
DJANGO_DEBUG=false
DJANGO_ALLOWED_HOSTS=your-domain.com,.your-domain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://your-domain.com,https://sub.your-domain.com
DJANGO_SECURE_SSL_REDIRECT=true
DJANGO_SESSION_COOKIE_SECURE=true
DJANGO_CSRF_COOKIE_SECURE=true
DJANGO_USE_X_FORWARDED_PROTO=true
```

## Database

Use PostgreSQL in production:

```env
DJANGO_DB_ENGINE=postgres
DJANGO_DB_NAME=candidate_ai
DJANGO_DB_USER=postgres
DJANGO_DB_PASSWORD=your_password
DJANGO_DB_HOST=localhost
DJANGO_DB_PORT=5432
```

## Vector Database

Qdrant should be reachable from the Django server:

```env
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION=candidate_embeddings
```

## Embeddings

### Ollama

```env
EMBEDDING_PROVIDER=ollama
EMBEDDING_MODEL=nomic-embed-text
OLLAMA_BASE_URL=http://localhost:11434
```

### OpenAI

```env
EMBEDDING_PROVIDER=openai
EMBEDDING_MODEL=text-embedding-3-small
OPENAI_API_KEY=your_openai_api_key
```

## Assistant Responses

```env
ASSISTANT_PROVIDER=openai
ASSISTANT_MODEL=gpt-5-mini
OPENAI_API_KEY=your_openai_api_key
```

## Vapi Webhook

Production server URL example:

```text
https://your-domain.com/api/vapi/hiring-assistant/
```

Make sure:

- the webhook URL is publicly reachable
- HTTPS is enabled
- the domain is included in `DJANGO_ALLOWED_HOSTS`
- the domain is included in `DJANGO_CSRF_TRUSTED_ORIGINS` if needed

## Deployment Checklist

1. Set `DJANGO_DEBUG=false`
2. Configure PostgreSQL
3. Configure Qdrant
4. Configure embeddings provider
5. Configure OpenAI assistant provider if needed
6. Run migrations
7. Restart Django app
8. Verify `/api/health/`
9. Verify `/api/vapi/hiring-assistant/`
10. Test candidate upload and chatbot search

## Notes

- Rotate any API keys that were exposed during development
- Do not use Django `runserver` in production
- Keep media storage and DB backups enabled
