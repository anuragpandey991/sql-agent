"""
main.py
FastAPI wrapper around the compiled LangGraph agent (app/graph.py).

Exposes a single /chat endpoint. Conversation history is kept per
session_id in an in-memory dict -- fine for a single-instance demo
deployment; would move to Redis/a DB for multi-instance production use
(noted in README as a scaling consideration).

Run locally:
    uvicorn main:app --reload

Then POST to http://localhost:8000/chat
"""

import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.graph import compiled_graph
from app.state import create_initial_state


# ============================================================
# In-memory session store
# session_id -> list[ChatTurn]
# ============================================================
SESSIONS: dict[str, list[dict]] = {}
MAX_HISTORY_TURNS = 6  # cap how many past turns get fed back into prompts


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Nothing to warm up currently, but this is the natural place to
    # do it (e.g. a DB connection pool) as the project grows.
    yield


app = FastAPI(
    title="SQL Query AI Agent",
    description="Converts natural language into SQL queries against an e-commerce database.",
    version="1.0.0",
    lifespan=lifespan,
)

# Permissive CORS for demo purposes -- a simple Streamlit/static frontend
# calling this from a different origin needs this. Tighten for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None  # if omitted, a new session is created


class ChatResponse(BaseModel):
    session_id: str
    answer: str
    sql: str | None = None
    intent: str | None = None
    result: list[dict] | None = None


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "SQL Query AI Agent is running. POST to /chat to interact.",
    }


@app.get("/health")
def health():
    return {"status": "healthy"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=400, detail="message must not be empty.")

    session_id = request.session_id or str(uuid.uuid4())
    history = SESSIONS.get(session_id, [])

    state = create_initial_state(request.message, chat_history=history)

    try:
        result = compiled_graph.invoke(state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent execution failed: {e}")

    # Persist this turn into session history for future requests
    new_turn = {
        "user_message": request.message,
        "assistant_message": result["final_answer"],
        "sql": result.get("generated_sql"),
    }
    history = history + [new_turn]
    SESSIONS[session_id] = history[-MAX_HISTORY_TURNS:]  # keep only recent turns

    return ChatResponse(
        session_id=session_id,
        answer=result["final_answer"],
        sql=result.get("generated_sql"),
        intent=result.get("intent"),
        result=result.get("query_result"),
    )


@app.post("/reset/{session_id}")
def reset_session(session_id: str):
    SESSIONS.pop(session_id, None)
    return {"status": "reset", "session_id": session_id}
