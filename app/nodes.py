"""
nodes.py
Each function here is a LangGraph "node": takes the current AgentState,
does one job, returns an updated AgentState. Kept as plain functions
(not classes) so the graph wiring in graph.py stays simple to read.
"""

import os
import json
import re
from dotenv import load_dotenv
from langchain_groq import ChatGroq

from app.state import AgentState
from app import db, validator
from app.prompts import (
    INTENT_CLASSIFICATION_PROMPT,
    SQL_GENERATION_PROMPT,
    SQL_REPAIR_PROMPT,
    ANSWER_FORMATTING_PROMPT,
    format_chat_history,
)

load_dotenv()

MODEL_NAME = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
llm = ChatGroq(model=MODEL_NAME, temperature=0)


def _extract_sql(raw_text: str) -> str:
    """Strips markdown code fences the model sometimes adds despite
    instructions not to, so downstream validation isn't tripped up by
    formatting noise rather than actual SQL problems.
    """
    text = raw_text.strip()
    text = re.sub(r"^```(sql)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


# ============================================================
# NODE 1: Intent classification
# ============================================================
def classify_intent(state: AgentState) -> AgentState:
    prompt = INTENT_CLASSIFICATION_PROMPT.format(
        chat_history=format_chat_history(state["chat_history"]),
        user_input=state["user_input"],
    )
    response = llm.invoke(prompt)
    raw = response.content.strip()

    # Defensive parsing: models occasionally wrap JSON in code fences
    # or add stray text despite instructions -- extract the JSON object.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    try:
        parsed = json.loads(match.group(0)) if match else json.loads(raw)
        intent = parsed.get("intent", "out_of_scope")
        reason = parsed.get("reason", "")
    except (json.JSONDecodeError, AttributeError):
        # If classification itself fails to parse, fail safe: treat as
        # out-of-scope rather than risk running an unvetted query.
        intent = "out_of_scope"
        reason = "Could not determine intent confidently."

    if intent not in ("in_scope", "out_of_scope", "write_operation"):
        intent = "out_of_scope"

    state["intent"] = intent
    state["rejection_reason"] = reason if intent != "in_scope" else None
    return state


# ============================================================
# NODE 2: Reject (out-of-scope or write-operation)
# ============================================================
def reject(state: AgentState) -> AgentState:
    if state["intent"] == "write_operation":
        state["final_answer"] = (
            "I can only answer questions about this database -- I can't "
            "insert, update, or delete data. Try rephrasing as a question "
            "about existing customers, products, or orders."
        )
    else:
        state["final_answer"] = (
            "That's outside what I can help with -- I can only answer "
            "questions about customers, products, orders, and order data "
            "in this database."
        )
    return state


# ============================================================
# NODE 3: Generate SQL
# ============================================================
def generate_sql(state: AgentState) -> AgentState:
    schema = db.get_schema_description()
    prompt = SQL_GENERATION_PROMPT.format(
        schema=schema,
        chat_history=format_chat_history(state["chat_history"]),
        user_input=state["user_input"],
    )
    response = llm.invoke(prompt)
    sql = _extract_sql(response.content)

    state["generated_sql"] = sql
    state["validation_errors"] = []
    return state


# ============================================================
# NODE 4: Validate SQL
# ============================================================
def validate_sql_node(state: AgentState) -> AgentState:
    sql = state["generated_sql"] or ""

    if sql.upper().startswith("NO_QUERY"):
        # The model itself flagged this as unanswerable from the schema --
        # treat it as a terminal (non-retryable) case.
        state["final_answer"] = (
            f"I can't answer that from this database: "
            f"{sql.split(':', 1)[1].strip() if ':' in sql else 'the required data is not available.'}"
        )
        state["validation_errors"] = ["NO_QUERY"]
        return state

    metadata = db.get_schema_metadata()
    errors = validator.validate_sql(sql, metadata)
    state["validation_errors"] = errors
    return state


# ============================================================
# NODE 5: Repair SQL (only reached if validation failed and retries remain)
# ============================================================
def repair_sql(state: AgentState) -> AgentState:
    schema = db.get_schema_description()
    prompt = SQL_REPAIR_PROMPT.format(
        schema=schema,
        user_input=state["user_input"],
        failed_sql=state["generated_sql"],
        errors="\n".join(state["validation_errors"]),
    )
    response = llm.invoke(prompt)
    sql = _extract_sql(response.content)

    state["generated_sql"] = sql
    state["retry_count"] += 1
    state["validation_errors"] = []
    return state


# ============================================================
# NODE 6: Execute SQL
# ============================================================
def execute_sql_node(state: AgentState) -> AgentState:
    try:
        rows = db.execute_query(state["generated_sql"])
        state["query_result"] = rows
        state["execution_error"] = None
    except Exception as e:
        state["query_result"] = None
        state["execution_error"] = str(e)
    return state


# ============================================================
# NODE 7: Format final natural-language answer
# ============================================================
def format_response(state: AgentState) -> AgentState:
    if state["execution_error"]:
        state["final_answer"] = (
            "I generated a query but it failed to run against the "
            f"database: {state['execution_error']}"
        )
        return state

    result = state["query_result"]
    prompt = ANSWER_FORMATTING_PROMPT.format(
        user_input=state["user_input"],
        sql=state["generated_sql"],
        result=json.dumps(result, default=str)[:4000],  # cap size defensively
    )
    response = llm.invoke(prompt)
    state["final_answer"] = response.content.strip()
    return state


# ============================================================
# NODE 8: Give up gracefully after max retries exhausted
# ============================================================
def give_up(state: AgentState) -> AgentState:
    state["final_answer"] = (
        "I wasn't able to generate a valid query for that after a few "
        "attempts. Could you try rephrasing your question, being more "
        "specific about which data you're looking for?"
    )
    return state
