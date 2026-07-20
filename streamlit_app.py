import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(
    page_title="SQL Query AI Agent",
    page_icon="🗄️",
    layout="centered",
)

st.title("🗄️ SQL Query AI Agent")
st.caption(
    "Ask questions about customers, products, and orders in plain English. "
    "The agent converts your question into SQL, validates it, and runs it "
    "against a live e-commerce database."
)

with st.expander("ℹ️ What can I ask?"):
    st.markdown(
        """
        **Examples that work well:**
        - "Show me the top 5 customers by total spend"
        - "How many orders are currently in 'delivered' status?"
        - "What products are in the Electronics category?"
        - "Now only show ones from Germany" *(as a follow-up)*

        **The agent will politely decline:**
        - Anything unrelated to this database (e.g. "what's the weather")
        - Any request to modify data (e.g. "delete all orders")
        - Questions needing data not in the schema (e.g. "what discount did they get")
        """
    )

if "messages" not in st.session_state:
    st.session_state.messages = []

if "session_id" not in st.session_state:
    st.session_state.session_id = None

with st.sidebar:
    st.subheader("Session")

    if st.session_state.session_id:
        st.code(st.session_state.session_id, language=None)
    else:
        st.write("(new session -- not started yet)")

    if st.button("🔄 Reset conversation"):
        if st.session_state.session_id:
            try:
                requests.post(
                    f"{API_URL}/reset/{st.session_state.session_id}",
                    timeout=5,
                )
            except requests.RequestException:
                pass

        st.session_state.messages = []
        st.session_state.session_id = None
        st.rerun()

    st.divider()
    st.caption(f"Backend: `{API_URL}`")

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

        if msg.get("sql"):
            with st.expander("View generated SQL"):
                st.code(msg["sql"], language="sql")

        if msg.get("result") is not None:
            with st.expander(
                f"View raw result ({len(msg['result'])} rows)"
            ):
                st.dataframe(msg["result"])

user_input = st.chat_input("Ask a question about the database...")

if user_input:
    st.session_state.messages.append(
        {"role": "user", "content": user_input}
    )

    with st.chat_message("user"):
        st.write(user_input)

    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            try:
                response = requests.post(
                    f"{API_URL}/chat",
                    json={
                        "message": user_input,
                        "session_id": st.session_state.session_id,
                    },
                    timeout=60,
                )
                response.raise_for_status()
                data = response.json()

                st.session_state.session_id = data["session_id"]
                answer = data["answer"]
                sql = data.get("sql")
                result = data.get("result")

                st.write(answer)

                if sql:
                    with st.expander("View generated SQL"):
                        st.code(sql, language="sql")

                if result is not None:
                    with st.expander(
                        f"View raw result ({len(result)} rows)"
                    ):
                        st.dataframe(result)

                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": answer,
                        "sql": sql,
                        "result": result,
                    }
                )

            except requests.exceptions.ConnectionError:
                error_msg = (
                    f"Could not reach the backend at `{API_URL}`. "
                    "Make sure the FastAPI server is running "
                    "(`uvicorn main:app --reload`)."
                )

                st.error(error_msg)
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": error_msg,
                    }
                )

            except requests.exceptions.RequestException as e:
                error_msg = f"Request failed: {e}"
                st.error(error_msg)
                st.session_state.messages.append(
                    {
                        "role": "assistant",
                        "content": error_msg,
                    }
                )
