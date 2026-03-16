# Candidate AI Backend

Django backend for an AI hiring assistant system with:

- Django auth for recruiters
- relational data in SQLite/PostgreSQL
- vector search in Qdrant
- CV parsing and candidate indexing
- chatbot-style candidate search endpoint with summary response

## Stack

- Django
- PostgreSQL or SQLite
- Qdrant
- GPT-5-mini as the planned assistant response model

## Embeddings

The project supports these embedding providers through environment settings:

- `placeholder`
- `ollama`
- `openai`

Example `.env` values:

```env
EMBEDDING_PROVIDER=placeholder
EMBEDDING_MODEL=gpt-5-mini

# For OpenAI
OPENAI_API_KEY=

# For Ollama
OLLAMA_BASE_URL=http://localhost:11434
```

## Assistant Responses

The project supports:

- `ASSISTANT_PROVIDER=placeholder`
- `ASSISTANT_PROVIDER=openai`

Example OpenAI config:

```env
ASSISTANT_PROVIDER=openai
ASSISTANT_MODEL=gpt-5-mini
OPENAI_API_KEY=your_key_here
```

## Setup

1. Install dependencies:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

2. Copy env file:

```powershell
Copy-Item .env.example .env
```

3. Choose database mode in `.env`:

- For quick local work:
  - `DJANGO_DB_ENGINE=sqlite`
- For project target setup:
  - `DJANGO_DB_ENGINE=postgres`
  - set `DJANGO_DB_NAME`, `DJANGO_DB_USER`, `DJANGO_DB_PASSWORD`, `DJANGO_DB_HOST`, `DJANGO_DB_PORT`

4. Run migrations:

```powershell
.venv\Scripts\python.exe manage.py migrate
```

5. Start Django:

```powershell
.venv\Scripts\python.exe manage.py runserver
```

## Qdrant

Run Qdrant locally with Docker:

```powershell
docker run -p 6333:6333 qdrant/qdrant
```

Qdrant config comes from:

- `QDRANT_URL`
- `QDRANT_COLLECTION`

## Important API paths

- `/api/health/`
- `/api/auth/register/`
- `/api/auth/login/`
- `/api/auth/me/`
- `/api/jobs/`
- `/api/jobs/dashboard/`
- `/api/candidates/`
- `/api/candidates/apply/`
- `/api/chatbot/search/`
- `/api/vapi/hiring-assistant/`

## Recommended next steps

- switch DB from SQLite to PostgreSQL
- connect a real embedding provider
- connect GPT-5-mini or another LLM provider for richer explanations
