Django backend for an AI-assisted hiring workflow with:

- hybrid search using semantic vectors plus keyword matching
- AI/LLM-enhanced resume parsing for skills, education, and experience
- background CV processing with Celery and Redis
- candidate fit scores with explainable ranking reasons
- job description embeddings for better job-specific matching
- bulk CV upload and Redis-backed search caching
- role-aware access for admins and recruiters
- production-ready Docker, Gunicorn, and Nginx setup

## Features

- Admin / Recruiter role-based access control
- Job CRUD APIs with stored job embeddings
- Async single and bulk candidate upload APIs
- Resume extraction from PDF, DOCX, and TXT
- Structured resume parsing via heuristics or OpenAI responses
- Qdrant semantic search plus database keyword reranking
- Explainable fit scoring and comparison APIs
- Dashboard with processing and fit metrics
- Vapi webhook integration for voice-driven recruiter queries

## Tech Stack

- Python / Django
- PostgreSQL or SQLite
- Redis
- Celery
- Qdrant
- Ollama or OpenAI for embeddings
- OpenAI for assistant/parser responses
- Gunicorn + Nginx

## Architecture

Primary stores and workers:

- relational DB for users, jobs, candidates, fit metadata, and upload state
- Redis for Celery broker/result backend and search caching
- Qdrant for candidate vector storage

High-level flow:

1. A recruiter creates a job.
2. The job description is normalized and embedded.
3. Candidates upload one or many resumes.
4. Upload requests return quickly while Celery processes files in the background.
5. Parsed resume signals, embeddings, fit scores, and ranking reasons are stored.
6. Hybrid search combines vector similarity, keyword overlap, skills, experience, and education.
7. Chatbot/search endpoints return ranked candidates plus explanation data.

## Local Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

3. Copy the environment template:

```powershell
Copy-Item .env.example .env
```

4. Start Redis and Qdrant:

```powershell
docker run -p 6379:6379 redis:7-alpine
docker run -p 6333:6333 qdrant/qdrant
```

5. If using PostgreSQL or Ollama, start those services too.
6. Run migrations:

```powershell
.venv\Scripts\python.exe manage.py migrate
```

7. Start Django:

```powershell
.venv\Scripts\python.exe manage.py runserver
```

8. Start Celery worker:

```powershell
.venv\Scripts\celery.exe -A candidate_ai worker -l info
```

## Core API Endpoints

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `GET /api/auth/me/`
- `GET /api/jobs/`
- `POST /api/jobs/`
- `GET /api/jobs/dashboard/`
- `POST /api/candidates/apply/`
- `POST /api/candidates/bulk-upload/`
- `GET /api/candidates/`
- `GET /api/candidates/<candidate_id>/summary/`
- `POST /api/chatbot/search/`
- `POST /api/chatbot/compare/`

## Production

Included deployment assets:

- [Dockerfile](/c:/Users/SIDRA/Documents/Project/candidate-ai-project/Dockerfile)
- [docker-compose.yml](/c:/Users/SIDRA/Documents/Project/candidate-ai-project/docker-compose.yml)
- [gunicorn.conf.py](/c:/Users/SIDRA/Documents/Project/candidate-ai-project/gunicorn.conf.py)
- [docker/nginx.conf](/c:/Users/SIDRA/Documents/Project/candidate-ai-project/docker/nginx.conf)

Bring up the full stack with:

```powershell
docker compose up --build
```

## Next Improvements

- Improve AI-based resume understanding for more accurate skills, experience, and education extraction.
- Show candidate fit score (%) for every candidate against each job.
- Implement hybrid search that combines semantic similarity with keyword matching.
- Add explainable ranking so the system clearly states why a candidate matched.
- Support bulk CV upload for recruiters managing many applicants at once.
- Expand recruiter dashboard with total applicants, top candidates, and hiring stats.
- Strengthen background processing so CV uploads remain fast while parsing runs asynchronously.
- Enhance duplicate CV detection to reduce repeated processing and noisy candidate data.
- Enforce role-based access control for Admin and Recruiter users.
- Keep the deployment stack production-ready with secure and scalable server infrastructure.

## Docs

- [docs/PROJECT_DOCUMENTATION.md](/c:/Users/SIDRA/Documents/Project/candidate-ai-project/docs/PROJECT_DOCUMENTATION.md)
- [docs/DEPLOYMENT.md](/c:/Users/SIDRA/Documents/Project/candidate-ai-project/docs/DEPLOYMENT.md)
