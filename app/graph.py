"""
graph.py
Wires the node functions from nodes.py into an actual LangGraph StateGraph
with conditional routing. This is the "agent" -- everything before this
file was building blocks; this is where they become one runnable pipeline.

Graph shape:

    START
      |
    classify_intent
      |
      +--(write_operation)--> reject --> END
      +--(out_of_scope)-----> reject --> END
      +--(in_scope)---------> generate_sql
                                  |
                              validate_sql_node
                                  |
                  +---(NO_QUERY / terminal)-------------------> END
                  +---(valid)---------------------------------> execute_sql_node --> format_response --> END
                  +---(invalid, retries remain)----------------> repair_sql --> validate_sql_node (loop)
                  +---(invalid, retries exhausted)--------------> give_up --> END
"""

from langgraph.graph import StateGraph, END

from app.state import AgentState
from app import nodes


# ============================================================
# Conditional routing functions
# ============================================================

def route_after_classification(state: AgentState) -> str:
    if state["intent"] == "in_scope":
        return "generate_sql"
    return "reject"


def route_after_validation(state: AgentState) -> str:
    errors = state["validation_errors"]

    # Model itself declared the question unanswerable -- terminal, not retryable.
    if errors == ["NO_QUERY"]:
        return "end"

    if not errors:
        return "execute_sql"

    if state["retry_count"] < state["max_retries"]:
        return "repair_sql"

    return "give_up"


# ============================================================
# Build the graph
# ============================================================

def build_graph():
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("classify_intent", nodes.classify_intent)
    graph.add_node("reject", nodes.reject)
    graph.add_node("generate_sql", nodes.generate_sql)
    graph.add_node("validate_sql", nodes.validate_sql_node)
    graph.add_node("repair_sql", nodes.repair_sql)
    graph.add_node("execute_sql", nodes.execute_sql_node)
    graph.add_node("format_response", nodes.format_response)
    graph.add_node("give_up", nodes.give_up)

    # Entry point
    graph.set_entry_point("classify_intent")

    # After classification: branch to generation or rejection
    graph.add_conditional_edges(
        "classify_intent",
        route_after_classification,
        {
            "generate_sql": "generate_sql",
            "reject": "reject",
        },
    )
    graph.add_edge("reject", END)

    # Generation always flows into validation
    graph.add_edge("generate_sql", "validate_sql")

    # After validation: branch to execute / repair (loop) / give up / end
    graph.add_conditional_edges(
        "validate_sql",
        route_after_validation,
        {
            "execute_sql": "execute_sql",
            "repair_sql": "repair_sql",
            "give_up": "give_up",
            "end": END,
        },
    )

    # Repair loops back into validation (bounded by max_retries)
    graph.add_edge("repair_sql", "validate_sql")

    # Execution flows into response formatting
    graph.add_edge("execute_sql", "format_response")
    graph.add_edge("format_response", END)
    graph.add_edge("give_up", END)

    return graph.compile()


# Compiled graph, ready to invoke from the API layer
compiled_graph = build_graph()


if __name__ == "__main__":
    from app.state import create_initial_state

    print("=== Running full graph: happy path ===")
    state = create_initial_state("What are the top 3 selling products by quantity?")
    result = compiled_graph.invoke(state)
    print("Intent:", result["intent"])
    print("SQL:", result["generated_sql"])
    print("Answer:", result["final_answer"])

    print("\n=== Running full graph: out-of-scope ===")
    state = create_initial_state("Tell me a joke")
    result = compiled_graph.invoke(state)
    print("Intent:", result["intent"])
    print("Answer:", result["final_answer"])

    print("\n=== Graph structure (Mermaid) ===")
    try:
        print(compiled_graph.get_graph().draw_mermaid())
    except Exception as e:
        print(f"(Mermaid rendering needs extra deps: {e})")
