# Applyze Backend API

FastAPI backend for Applyze Phase 1.

## Features

- **FastAPI** - Modern, fast web framework for building APIs
- **Pydantic** - Data validation using Python type annotations
- **CORS** - Cross-Origin Resource Sharing enabled
- **Mock Data** - Ready-to-use mock endpoints for development

## API Endpoints

### Jobs
- `GET /api/v1/jobs/` - Get all jobs
- `GET /api/v1/jobs/{id}` - Get job by ID
- `POST /api/v1/jobs/` - Create new job
- `PUT /api/v1/jobs/{id}` - Update job
- `DELETE /api/v1/jobs/{id}` - Delete job

### Users
- `GET /api/v1/users/` - Get all users
- `GET /api/v1/users/{id}` - Get user by ID
- `POST /api/v1/users/` - Create new user
- `PUT /api/v1/users/{id}` - Update user

## Setup

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Copy environment file:
```bash
cp .env.example .env
```

3. Run the server:
```bash
uvicorn app.main:app --reload
```

The API will be available at `http://localhost:8000`
API documentation at `http://localhost:8000/docs`
