# AI Candidate Recommendation System

Django backend for an AI-assisted hiring workflow that helps recruiters:

- create and manage jobs
- collect candidate applications and resumes
- parse resume text
- generate embeddings
- store candidate vectors in Qdrant
- search and rank candidates for a hiring query
- expose the workflow through chatbot APIs and a Vapi voice assistant webhook

## Features

- Recruiter authentication
- Job CRUD APIs
- Candidate application API with PDF resume upload
- Resume text extraction
- Embedding support through `placeholder`, `ollama`, or `openai`
- Qdrant-based semantic candidate search
- Skill-aware reranking
- Candidate comparison and summary endpoints
- Vapi webhook integration for voice-driven recruiter queries
- Basic dashboard/reporting endpoint

## Tech Stack

- Python
- Django
- PostgreSQL or SQLite
- Qdrant
- Ollama or OpenAI for embeddings
- OpenAI for assistant-style responses
- Vapi for voice assistant integration

## Architecture

This project uses two data stores:

- PostgreSQL or SQLite for application data such as users, jobs, and candidates
- Qdrant for vector embeddings and semantic search

High-level flow:

1. A recruiter creates a job.
2. A candidate uploads a resume.
3. The backend extracts resume text.
4. The text is converted into embeddings.
5. Candidate vectors are stored in Qdrant.
6. A recruiter query is embedded and searched against indexed candidates.
7. Results are reranked and returned as a structured answer.

## Project Structure

```text
candidate-ai-project/
├── candidate_ai/
├── apps/
│   ├── accounts/
│   ├── ai/
│   ├── candidates/
│   ├── chatbot/
│   ├── jobs/
│   └── vapi/
├── docs/
├── manage.py
├── requirements.txt
└── .env.example
```

## Environment Configuration

Copy the example file and set your own values:

```powershell
Copy-Item .env.example .env
```

Important:

- `.env` is intentionally not committed
- do not publish API keys, passwords, or private hostnames
- use your own local or deployment-specific values

Main environment groups:

- Django settings
- database settings
- Qdrant settings
- embedding provider settings
- assistant provider settings
- Vapi settings

See [.env.example](.env.example) for the full template.

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

4. Choose a database in `.env`:

- quick local setup:
  - `DJANGO_DB_ENGINE=sqlite`
- recommended project setup:
  - `DJANGO_DB_ENGINE=postgres`

5. Start Qdrant locally:

```powershell
docker run -p 6333:6333 qdrant/qdrant
```

6. If using Ollama embeddings, make sure Ollama is running:

```powershell
ollama serve
```

7. Run migrations:

```powershell
.venv\Scripts\python.exe manage.py migrate
```

8. Start the Django server:

```powershell
.venv\Scripts\python.exe manage.py runserver
```

## Supported Providers

### Embeddings

- `placeholder`
- `ollama`
- `openai`

### Assistant Responses

- `placeholder`
- `openai`

## Core API Endpoints

### System

- `GET /api/health/`

### Authentication

- `POST /api/auth/register/`
- `POST /api/auth/login/`
- `POST /api/auth/logout/`
- `GET /api/auth/me/`

### Jobs

- `GET /api/jobs/`
- `POST /api/jobs/`
- `GET /api/jobs/dashboard/`
- `GET /api/jobs/<job_id>/`
- `PATCH /api/jobs/<job_id>/`
- `DELETE /api/jobs/<job_id>/`

### Candidates

- `GET /api/candidates/`
- `POST /api/candidates/apply/`
- `GET /api/candidates/<candidate_id>/summary/`

### Chatbot

- `POST /api/chatbot/search/`
- `POST /api/chatbot/compare/`

### Vapi

- `GET /api/vapi/hiring-assistant/`
- `POST /api/vapi/hiring-assistant/`

For request bodies and Postman examples, see:

- [docs/API_TESTING.md](docs/API_TESTING.md)
- [docs/postman/Candidate-AI-Backend.postman_collection.json](docs/postman/Candidate-AI-Backend.postman_collection.json)

## Public Repository Safety

These files are intentionally excluded from Git:

- `.env`
- `.venv/`
- `db.sqlite3`
- `media/`
- `ngrok.exe`

Do not commit:

- OpenAI keys
- database passwords
- private ngrok URLs if you do not want them public
- production secrets
- local uploaded resumes

## Notes

- PDF upload is currently enforced for candidate resumes.
- Candidate search supports both `job_id` and `job_title`.
- Voice assistant behavior depends on Vapi, your configured voice model, and your `.env` values.

## Documentation

- [docs/PROJECT_DOCUMENTATION.md](docs/PROJECT_DOCUMENTATION.md)
- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)

## License

No license file is included in this repository yet.
