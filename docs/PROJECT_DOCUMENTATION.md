# Project Documentation

## Project Title

AI Hiring Assistant and Resume Screening System

## Introduction

This project is a Django-based backend system that automates candidate screening for job recruitment. Instead of manually reviewing a large number of CVs, the system processes resumes, generates embeddings, stores them in a vector database, and returns the most relevant candidates for a job through semantic search.

The project uses two databases:

- PostgreSQL for structured application data
- Qdrant for embeddings and vector similarity search

The system also supports AI-driven candidate matching and chatbot-style search responses.

## Problem Statement

In a hiring process, a single job can receive dozens or even hundreds of CVs. Manually reviewing these applications is slow, repetitive, and error-prone. Recruiters may miss highly relevant candidates because of time constraints or human bias.

The goal of this project is to automate CV screening and candidate ranking by comparing job requirements with candidate resumes using embeddings and semantic search.

## Objectives

- Build a backend system for job and candidate management
- Allow recruiters to create jobs and candidates to apply with resumes
- Extract text from uploaded CV files
- Convert CVs and queries into embeddings
- Store embeddings in Qdrant for similarity search
- Rank candidates according to job relevance
- Return recruiter-friendly chatbot responses

## Scope

The current project scope is backend only. It includes authentication, job creation, candidate application, CV parsing, embeddings generation, vector search, and chatbot-style response generation. Frontend is not part of the current implementation.

## Technologies Used

- Django
- PostgreSQL
- Qdrant
- Ollama
- Python
- Docker
- Postman

## System Architecture

The system works in two layers:

### 1. Relational Data Layer

PostgreSQL stores:

- users
- jobs
- candidates
- application metadata

### 2. Vector Search Layer

Qdrant stores:

- CV embeddings
- similarity-ready vectors
- candidate payload data linked to vectors

## Core Concepts

### Embeddings

Embeddings are numerical representations of text. The project converts CV text and recruiter queries into vectors so the system can compare meaning rather than exact words.

### Semantic Search

Instead of traditional keyword search, the system compares vector similarity to find the most relevant candidates.

### Vector Database

Qdrant is used because it is optimized for storing embeddings and performing similarity search quickly.

### RAG-style Flow

The project follows a retrieval-first pattern:

- retrieve relevant candidates from Qdrant
- generate a human-readable response from the retrieved results

## Modules

### Authentication Module

Handles:

- user registration
- login
- logout
- current user lookup

### Jobs Module

Handles:

- create job
- list jobs
- view job detail
- update job
- delete job

### Candidates Module

Handles:

- candidate application
- CV upload
- resume text extraction
- candidate listing
- duplicate resume detection
- experience and education heuristics

### AI Module

Handles:

- embeddings generation
- document parsing
- vector indexing
- candidate reranking
- experience-aware and education-aware scoring

### Chatbot Module

Handles:

- recruiter query intake
- vector search
- candidate matching response
- summary generation

## Workflow

### Candidate Upload Flow

1. Recruiter creates a job
2. Candidate applies for that job
3. CV file is uploaded
4. Resume text is extracted
5. Embedding is generated
6. Embedding is stored in Qdrant
7. Candidate record is stored in PostgreSQL

### Recruiter Search Flow

1. Recruiter sends a search query
2. Query is converted into an embedding
3. Qdrant searches for the nearest candidate vectors
4. Candidates are reranked using skill overlap
5. Chatbot returns the best candidate and other relevant matches

## Why Two Databases Are Used

Two databases are necessary because the project handles two different kinds of data:

- PostgreSQL is best for structured relational records
- Qdrant is best for embeddings and semantic search

If only PostgreSQL were used, semantic similarity search would not be efficient. If only Qdrant were used, normal application data management would become weak and inconvenient.

## Current Implementation Status

Completed:

- Django backend setup
- PostgreSQL integration
- Qdrant integration
- candidate upload flow
- CV text extraction
- Ollama embedding configuration
- semantic candidate search
- ranking improvement using skill overlap
- resume content duplicate protection
- PDF-only upload enforcement
- dashboard/reporting endpoint
- Postman testing collection

## Sample API Flow

1. `POST /api/auth/register/`
2. `POST /api/auth/login/`
3. `POST /api/jobs/`
4. `POST /api/candidates/apply/`
5. `POST /api/chatbot/search/`

## Testing

The APIs were tested using Postman. The system was verified for:

- authentication flow
- job creation
- candidate resume upload
- vector indexing
- candidate search
- chatbot response generation

## Results

The project successfully retrieves and ranks candidates based on recruiter queries. It can distinguish between relevant backend candidates and unrelated frontend candidates, and it returns a structured and human-readable answer.

## Limitations

- experience and education scoring currently use heuristics from resume text, not a specialized HR model
- resume parsing can be improved further for complex PDF layouts
- frontend dashboard UI is not implemented yet; backend dashboard data endpoint is available

## Future Improvements

- improve AI-based resume understanding for more accurate skills, experience, and education extraction
- show candidate fit score (%) for every candidate against each job
- implement hybrid search that combines semantic similarity with keyword matching
- add explainable ranking so the system clearly states why a candidate matched
- support bulk CV upload for recruiters managing many applicants at once
- expand recruiter dashboard with total applicants, top candidates, and hiring stats
- strengthen background processing so CV uploads remain fast while parsing runs asynchronously
- enhance duplicate CV detection to reduce repeated processing and noisy candidate data
- enforce role-based access control for Admin and Recruiter users
- keep the deployment stack production-ready with secure and scalable server infrastructure

## Conclusion

This project demonstrates a complete backend pipeline for AI-based hiring assistance. It combines Django, PostgreSQL, Qdrant, and embeddings-based semantic search to automate candidate matching and ranking. The system reduces manual effort, improves recruiter efficiency, and provides a strong foundation for an intelligent hiring platform.
