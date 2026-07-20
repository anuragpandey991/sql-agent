import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.graph import compiled_graph
from app.state import create_initial_state


SESSIONS: dict[str, list[dict]] = {}
MAX_HISTORY_TURNS = 6


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="SQL Query AI Agent",
    description="Converts natural language into SQL queries against an e-commerce database.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


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

    new_turn = {
        "user_message": request.message,
        "assistant_message": result["final_answer"],
        "sql": result.get("generated_sql"),
    }

    history = history + [new_turn]
    SESSIONS[session_id] = history[-MAX_HISTORY_TURNS:]

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
