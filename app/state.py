from typing import Literal, Optional, TypedDict


class ChatTurn(TypedDict):
    user_message: str
    assistant_message: str
    sql: Optional[str]


class AgentState(TypedDict):
    user_input: str
    chat_history: list[ChatTurn]

    intent: Optional[
        Literal[
            "in_scope",
            "out_of_scope",
            "write_operation",
        ]
    ]
    rejection_reason: Optional[str]

    generated_sql: Optional[str]
    validation_errors: list[str]
    retry_count: int
    max_retries: int

    query_result: Optional[list[dict]]
    execution_error: Optional[str]

    final_answer: Optional[str]


def create_initial_state(
    user_input: str,
    chat_history: list[ChatTurn] | None = None,
) -> AgentState:
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
