"""
Simple University Notes Assistant
---------------------------------
This file keeps the project intentionally compact so you can clearly see how:
1) FastAPI serves the frontend
2) File upload works
3) PDF ingestion works
4) Chroma stores embeddings
5) Retrieval + LLM answering works

Later, we can split this into modules/routes/services.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# LangChain / RAG imports
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Load environment variables from .env if it exists
load_dotenv()
print("DEBUG KEY:", os.getenv("OPENAI_API_KEY"))

# -----------------------------
# Basic path setup
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
CHROMA_DIR = DATA_DIR / "chroma_db"
STATE_FILE = DATA_DIR / "state.json"

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
CHROMA_DIR.mkdir(parents=True, exist_ok=True)

# -----------------------------
# FastAPI app setup
# -----------------------------
app = FastAPI(title="University Notes Assistant")

# CORS is helpful in development, even though our frontend is served by FastAPI itself
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "app" / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "app" / "templates"))

# -----------------------------
# Simple config values
# -----------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gpt-4o-mini")

# Chunking config for large university notes / books
CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1200"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))

# Chroma collection name
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "university_notes")

# -----------------------------
# Utility helpers
# -----------------------------
def load_state() -> dict[str, Any]:
    """Load small app state from a JSON file.

    We are NOT storing chat history here.
    We only keep document-related status, such as:
    - uploaded filename
    - upload path
    - whether ingestion happened
    - chunk count
    """
    if not STATE_FILE.exists():
        return {
            "uploaded_filename": None,
            "uploaded_filepath": None,
            "ingested": False,
            "chunks_count": 0,
        }
    with STATE_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_state(state: dict[str, Any]) -> None:
    """Persist the small app state to disk."""
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def require_openai_key() -> None:
    """Raise a clear error if the user forgot the API key."""
    if not OPENAI_API_KEY:
        raise HTTPException(
            status_code=500,
            detail=(
                "OPENAI_API_KEY is missing. Add it to your .env file before "
                "using ingestion or asking questions."
            ),
        )


def get_embeddings() -> OpenAIEmbeddings:
    """Create the embedding model object."""
    require_openai_key()
    return OpenAIEmbeddings(model=EMBEDDING_MODEL)


def get_llm() -> ChatOpenAI:
    """Create the chat model object."""
    require_openai_key()
    return ChatOpenAI(model=CHAT_MODEL, temperature=0)


def get_vectorstore() -> Chroma:
    """Load the persisted Chroma vector store."""
    return Chroma(
        collection_name=COLLECTION_NAME,
        persist_directory=str(CHROMA_DIR),
        embedding_function=get_embeddings(),
    )


def clear_existing_collection() -> None:
    """Delete all currently stored vectors from the active collection.

    For this first simple version, we keep only ONE active document collection.
    That keeps the mental model simple while you learn the whole flow.
    """
    vectorstore = get_vectorstore()
    try:
        vectorstore.delete_collection()
    except Exception:
        # If the collection doesn't exist yet, that's okay.
        pass


def format_sources(docs: list[Any]) -> list[dict[str, Any]]:
    """Convert retrieved LangChain docs into simple JSON-friendly source blocks."""
    sources = []
    for doc in docs:
        metadata = doc.metadata or {}
        sources.append(
            {
                "file": metadata.get("source", "unknown"),
                "page": metadata.get("page", None),
                "excerpt": doc.page_content[:300].strip(),
            }
        )
    return sources


# -----------------------------
# Page routes
# -----------------------------
@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    """Serve the single frontend page."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={}
    );

# -----------------------------
# API routes
# -----------------------------
@app.get("/health")
async def health() -> dict[str, str]:
    """Simple health check."""
    return {"status": "ok"}


@app.get("/status")
async def status() -> dict[str, Any]:
    """Return current document status so the frontend can show it."""
    return load_state()


@app.post("/upload")
async def upload_file(file: UploadFile = File(...)) -> JSONResponse:
    """
    Upload a PDF file and save it to disk.

    We keep upload separate from ingest because large books can take time
    to process. This is a cleaner product design.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file selected.")

    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed in this version.")

    safe_name = Path(file.filename).name
    destination = UPLOAD_DIR / safe_name

    # Save uploaded file to the uploads directory
    with destination.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    state = load_state()
    state["uploaded_filename"] = safe_name
    state["uploaded_filepath"] = str(destination)
    state["ingested"] = False
    state["chunks_count"] = 0
    save_state(state)

    return JSONResponse(
        {
            "message": "File uploaded successfully.",
            "filename": safe_name,
            "filepath": str(destination),
        }
    )


@app.post("/ingest")
async def ingest_document() -> JSONResponse:
    """
    Read the uploaded PDF, split it into chunks, create embeddings,
    and store everything in Chroma.

    For simplicity:
    - we ingest one active file at a time
    - we replace the old collection on each new ingest
    """
    state = load_state()
    filepath = state.get("uploaded_filepath")

    if not filepath:
        raise HTTPException(status_code=400, detail="No uploaded file found. Upload a PDF first.")

    file_path = Path(filepath)
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Uploaded file not found on disk.")

    require_openai_key()

    # 1) Load PDF
    loader = PyPDFLoader(str(file_path))
    documents = loader.load()

    if not documents:
        raise HTTPException(status_code=400, detail="No readable content found in the PDF.")

    # 2) Split into chunks
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    chunks = splitter.split_documents(documents)

    if not chunks:
        raise HTTPException(status_code=400, detail="Chunking failed. No chunks were created.")

    # Add a simple chunk index to metadata to help debugging and source display
    for idx, chunk in enumerate(chunks):
        chunk.metadata = chunk.metadata or {}
        chunk.metadata["chunk_index"] = idx
        chunk.metadata["source"] = file_path.name

    # 3) Clear previous collection for this simple MVP
    clear_existing_collection()

    # 4) Build a fresh vector store from chunks
    _ = Chroma.from_documents(
        documents=chunks,
        embedding=get_embeddings(),
        persist_directory=str(CHROMA_DIR),
        collection_name=COLLECTION_NAME,
    )

    state["ingested"] = True
    state["chunks_count"] = len(chunks)
    save_state(state)

    return JSONResponse(
        {
            "message": "Document ingested successfully.",
            "filename": file_path.name,
            "chunks_count": len(chunks),
        }
    )


@app.post("/ask")
async def ask_question(request: Request) -> JSONResponse:
    """
    Ask a question about the uploaded notes.

    Important:
    - This version does NOT send old chat messages back to the model.
    - Each question is answered independently.
    - The frontend only keeps previous messages visible on screen.
    """
    state = load_state()

    if not state.get("ingested"):
        raise HTTPException(
            status_code=400,
            detail="No ingested document found. Upload and ingest a PDF first.",
        )

    payload = await request.json()
    question = (payload.get("question") or "").strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    vectorstore = get_vectorstore()

    # Retriever: get the top relevant chunks
    retriever = vectorstore.as_retriever(search_kwargs={"k": 4})
    docs = retriever.invoke(question)

    if not docs:
        return JSONResponse(
            {
                "answer": (
                    "I could not find enough relevant information in the uploaded notes "
                    "to answer that question."
                ),
                "sources": [],
            }
        )

    # Build the context manually so the flow is easy to understand
    context_blocks = []
    for i, doc in enumerate(docs, start=1):
        metadata = doc.metadata or {}
        page = metadata.get("page", "unknown")
        source = metadata.get("source", "unknown")
        context_blocks.append(
            f"[Source {i} | file={source} | page={page}]\n{doc.page_content}"
        )

    context_text = "\n\n".join(context_blocks)

    prompt = f"""
You are a helpful university study assistant.

Answer the student's question using ONLY the context below.
Rules:
1. If the answer is not clearly supported by the context, say so honestly.
2. Explain in simple words suitable for exam preparation.
3. Keep the answer focused and easy to study.
4. Do not invent facts that are not in the notes.

Student question:
{question}

Context:
{context_text}
""".strip()

    llm = get_llm()
    result = llm.invoke(prompt)
    answer_text = result.content if hasattr(result, "content") else str(result)

    return JSONResponse(
        {
            "answer": answer_text,
            "sources": format_sources(docs),
        }
    )
