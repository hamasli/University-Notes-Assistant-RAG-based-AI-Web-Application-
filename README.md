# University Notes Assistant

A simple product-style RAG web app for uploading university notes and asking exam-preparation questions.

## Features

- Upload a PDF
- Ingest the PDF into Chroma
- Ask questions from the notes
- See all Q/A blocks on the page
- FastAPI frontend + backend in one project
- Dockerized
- Uses `uv` for dependency management

## Simple project structure

```text
university-notes-assistant/
├── app/
│   ├── main.py
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── style.css
│       └── main.js
├── data/
│   ├── uploads/
│   └── chroma_db/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## Local setup with uv

### 1) Create `.env`
Copy `.env.example` to `.env` and add your real OpenAI key.

### 2) Install dependencies
```bash
uv sync
```

### 3) Run the app
```bash
uv run uvicorn app.main:app --reload
```

### 4) Open in browser
```text
http://127.0.0.1:8000
```

## Docker setup

### Build and run
```bash
docker compose up --build
```

Then open:

```text
http://127.0.0.1:8000
```

## Notes

- This first version keeps all logic intentionally simple and visible.
- Chat history is **not stored in the backend** yet.
- Old messages stay visible on the frontend only.
- Each question is answered independently.
- Later we can split the code into routes/services/schemas.
