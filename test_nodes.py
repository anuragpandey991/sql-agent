"""
test_nodes.py
Smoke-tests each node function individually (without LangGraph wiring yet)
to isolate node logic bugs from graph-wiring bugs.

Usage:
    python test_nodes.py
"""

from app.state import create_initial_state
from app import nodes


def run_happy_path():
    print("=== TEST 1: In-scope question (happy path) ===")
    state = create_initial_state("Show me the top 3 customers by total spend")

    state = nodes.classify_intent(state)
    print("Intent:", state["intent"])
    assert state["intent"] == "in_scope", "Expected in_scope classification"

    state = nodes.generate_sql(state)
    print("Generated SQL:", state["generated_sql"])

    state = nodes.validate_sql_node(state)
    print("Validation errors:", state["validation_errors"])

    if not state["validation_errors"]:
        state = nodes.execute_sql_node(state)
        print("Query result:", state["query_result"])
        state = nodes.format_response(state)
        print("Final answer:", state["final_answer"])
    print()


def run_out_of_scope():
    print("=== TEST 2: Out-of-scope question ===")
    state = create_initial_state("What's the weather like today?")
    state = nodes.classify_intent(state)
    print("Intent:", state["intent"])
    assert state["intent"] == "out_of_scope", "Expected out_of_scope classification"

    state = nodes.reject(state)
    print("Final answer:", state["final_answer"])
    print()


def run_write_operation():
    print("=== TEST 3: Write-operation attempt ===")
    state = create_initial_state("Delete all orders from customers in India")
    state = nodes.classify_intent(state)
    print("Intent:", state["intent"])
    assert state["intent"] == "write_operation", "Expected write_operation classification"

    state = nodes.reject(state)
    print("Final answer:", state["final_answer"])
    print()


def run_hallucination_trap():
    print("=== TEST 4: Schema-violating question (discount doesn't exist) ===")
    state = create_initial_state("What discount did each customer receive?")
    state = nodes.classify_intent(state)
    print("Intent:", state["intent"])

    state = nodes.generate_sql(state)
    print("Generated SQL:", state["generated_sql"])

    state = nodes.validate_sql_node(state)
    print("Validation errors:", state["validation_errors"])
    print("Final answer (if NO_QUERY triggered):", state.get("final_answer"))
    print()


def run_multiturn_context():
    print("=== TEST 5: Multi-turn context (follow-up question) ===")
    state = create_initial_state("Show top 5 customers by total spend")
    state = nodes.classify_intent(state)
    state = nodes.generate_sql(state)
    state = nodes.validate_sql_node(state)
    state = nodes.execute_sql_node(state)
    state = nodes.format_response(state)
    print("Turn 1 SQL:", state["generated_sql"])
    print("Turn 1 answer:", state["final_answer"])

    # simulate carrying history into turn 2
    history = [{
        "user_message": state["user_input"],
        "assistant_message": state["final_answer"],
        "sql": state["generated_sql"],
    }]

    state2 = create_initial_state("Now only show ones from Germany", chat_history=history)
    state2 = nodes.classify_intent(state2)
    state2 = nodes.generate_sql(state2)
    state2 = nodes.validate_sql_node(state2)
    print("\nTurn 2 SQL:", state2["generated_sql"])
    print("Turn 2 validation errors:", state2["validation_errors"])
    print()


if __name__ == "__main__":
    run_happy_path()
    run_out_of_scope()
    run_write_operation()
    run_hallucination_trap()
    run_multiturn_context()
    print("✅ All node smoke tests completed.")
