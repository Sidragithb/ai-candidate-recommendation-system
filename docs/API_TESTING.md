# API Testing Guide

Base URL:

```text
http://127.0.0.1:8000
```

## Test Order

1. `GET /api/health/`
2. `POST /api/auth/register/`
3. `POST /api/auth/login/`
4. `POST /api/jobs/`
5. `GET /api/jobs/`
6. `GET /api/jobs/dashboard/`
7. `POST /api/candidates/apply/`
8. `GET /api/candidates/?job_id=<job_id>`
9. `GET /api/candidates/<candidate_id>/summary/`
10. `POST /api/chatbot/search/`
11. `POST /api/chatbot/compare/`

## 1. Health Check

- Method: `GET`
- URL: `/api/health/`

Expected:

```json
{
  "status": "ok",
  "framework": "django"
}
```

## 2. Register

- Method: `POST`
- URL: `/api/auth/register/`
- Body: `raw` -> `JSON`

```json
{
  "username": "sidra1",
  "email": "sidra1@example.com",
  "password": "test12345"
}
```

## 3. Login

- Method: `POST`
- URL: `/api/auth/login/`
- Body: `raw` -> `JSON`

```json
{
  "username": "sidra1",
  "password": "test12345"
}
```

Note:

- Postman must keep cookies after login.
- Use the same collection/session for later requests.

## 4. Create Job

- Method: `POST`
- URL: `/api/jobs/`
- Body: `raw` -> `JSON`

```json
{
  "title": "Python Developer",
  "description": "Need Python, Django, and PostgreSQL skills",
  "required_skills": ["Python", "Django", "PostgreSQL"]
}
```

Save the returned `id` as `job_id`.

## 5. List Jobs

- Method: `GET`
- URL: `/api/jobs/`

## 6. Apply Candidate

- Method: `POST`
- URL: `/api/candidates/apply/`
- Body: `form-data`

Fields:

- `job_id` -> Text
- `full_name` -> Text
- `email` -> Text
- `skills` -> Text
- `resume` -> File

Validation rules:

- resume file is required
- allowed file types: `.pdf` only
- same email cannot apply twice for the same job
- same resume content cannot be uploaded twice for the same job

Example:

- `job_id`: `2`
- `full_name`: `Ahmed Khan`
- `email`: `ahmed@gmail.com`
- `skills`: `Python,Django,PostgreSQL`
- `resume`: `ahmed_cv.pdf`

## 7. List Candidates

- Method: `GET`
- URL: `/api/candidates/?job_id=2`

## 8. Dashboard Overview

- Method: `GET`
- URL: `/api/jobs/dashboard/`

Expected response includes:

- total jobs
- total candidates
- indexed candidates
- top skills
- per-job candidate counts

## 9. Chatbot Search

- Method: `POST`
- URL: `/api/chatbot/search/`
- Body: `raw` -> `JSON`

```json
{
  "query": "best python django candidate",
  "job_id": 2,
  "limit": 5
}
```

You can also search by job title instead of job ID:

```json
{
  "query": "best python django candidate",
  "job_title": "Python Developer",
  "limit": 5
}
```

Expected response shape:

```json
{
  "query": "best python django candidate",
  "matches": [],
  "answer": "Best match ...",
  "summary": {
    "query": "best python django candidate",
    "job_id": 2,
    "total_matches": 0,
    "top_candidate": null
  }
}
```

## Suggested Test Candidates

### Ahmed Khan

- Skills: `Python,Django,PostgreSQL`
- Resume focus: Django backend

### Sara Ali

- Skills: `React,JavaScript,Frontend,HTML,CSS`
- Resume focus: frontend

### Usman Tariq

- Skills: `Python,FastAPI,REST,PostgreSQL`
- Resume focus: FastAPI backend

## Expected Ranking Example

For the query:

```json
{
  "query": "best python django candidate",
  "job_id": 2,
  "limit": 5
}
```

Expected order should generally prefer:

1. Django backend candidates
2. Python backend candidates without Django
3. Unrelated frontend candidates

## 10. Candidate Summary

- Method: `GET`
- URL: `/api/candidates/1/summary/`

Expected response includes:

- candidate profile
- job title
- skills summary
- resume excerpt

## 11. Compare Candidates

- Method: `POST`
- URL: `/api/chatbot/compare/`
- Body: `raw` -> `JSON`

```json
{
  "candidate_ids": [1, 2, 3],
  "query": "Compare python django backend candidates for job 1"
}
```

Expected response includes:

- compared candidate list
- best candidate
- matched skills
- comparison answer
