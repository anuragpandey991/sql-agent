"""
state.py
Defines the shared State object that flows through the LangGraph.

Every node reads from and writes to this State. Keeping it explicit and
typed (rather than a loose dict) makes the graph's data flow self-documenting --
you can look at this one file to understand exactly what information is
available at every step of the pipeline.
"""

from typing import TypedDict, Literal, Optional


class ChatTurn(TypedDict):
    """A single past exchange, kept for conversation-context resolution."""
    user_message: str
    assistant_message: str
    sql: Optional[str]  # the SQL generated for this turn, if any


class AgentState(TypedDict):
    # --- input for this turn ---
    user_input: str  # the raw message just received from the user

    # --- conversation memory ---
    chat_history: list[ChatTurn]  # all prior turns in this session

    # --- intent classification ---
    intent: Optional[Literal["in_scope", "out_of_scope", "write_operation"]]
    rejection_reason: Optional[str]  # populated only if intent != in_scope

    # --- SQL generation / validation loop ---
    generated_sql: Optional[str]
    validation_errors: list[str]  # errors from the current validation attempt
    retry_count: int  # how many repair attempts have been made this turn
    max_retries: int  # cap to prevent infinite loops (set once at graph entry)

    # --- execution ---
    query_result: Optional[list[dict]]  # rows returned from execute_query
    execution_error: Optional[str]  # populated if the DB itself raised an error

    # --- final output for this turn ---
    final_answer: Optional[str]  # natural-language answer shown to the user


def create_initial_state(user_input: str, chat_history: list[ChatTurn] | None = None) -> AgentState:
    """Factory for a fresh per-turn state. Chat history is carried over
    from the previous turn (passed in by the caller / API layer);
    everything else resets each turn.
    """
    return AgentState(
        user_input=user_input,
        chat_history=chat_history or [],
        intent=None,
        rejection_reason=None,
        generated_sql=None,
        validation_errors=[],
        retry_count=0,
        max_retries=2,
        query_result=None,
        execution_error=None,
        final_answer=None,
    )
