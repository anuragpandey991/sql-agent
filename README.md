# SQL Query AI Agent

A task-oriented AI agent that converts natural language questions into safe, validated SQL queries against a live e-commerce database — built with **LangGraph**, **Groq (Llama 3.3 70B)**, **FastAPI**, and **Streamlit**.

Built for the Forward Deployed Engineer technical assignment.

---

## Live Links

| | |
|---|---|
| **Live App** | https://your-app.streamlit.app |
| **API Docs (Swagger)** | https://sql-agent-1-0vkn.onrender.com/docs |
| **GitHub Repo** | https://github.com/anuragpandey991/sql-agent |
| **Demo Video** | https://drive.google.com/file/d/1U7VokfQ6WGT-YOAryYXUPaIqlz_FrS0v/view?usp=sharing |
| **Presentation** | https://docs.google.com/presentation/d/1UDgTfVhdcp6dWFWUtD1_SlJAxd4hciaKthSWrgNOfFc/edit?usp=sharing |
| **Mermaid Diagram** | https://mermaid.ai/app/projects/11959721-909a-464f-813c-44319e890de0/diagrams/177177dc-fb0e-4f67-9032-edee2dd24328/version/v0.1/edit |



> **Note:** The backend runs on Render's free tier, which spins down after ~15 minutes of inactivity. The first request after idle time may take 30–60 seconds to respond while the service wakes up.

---

## What It Does

Ask questions in plain English — "show me the top 5 customers by total spend" — and the agent:

1. **Classifies intent** — is this answerable from the database, unrelated, or a request to modify data?
2. **Generates SQL** — grounded in the actual live schema, using few-shot examples
3. **Validates deterministically** — parses the SQL, blocks anything that isn't a `SELECT`, checks every table/column reference against the real schema
4. **Repairs on failure** — if validation fails, the exact error is fed back for a bounded retry (max 2 attempts)
5. **Executes safely** — only reachable after validation passes, against a read-only database connection
6. **Responds naturally** — formats the raw result into a plain-language answer
7. **Remembers the conversation** — follow-up questions like "now only from Germany" resolve correctly using prior turns

It also does the reverse well: it declines out-of-scope questions, refuses write operations (`DELETE`, `DROP`, etc.), and admits when the schema genuinely doesn't have the data being asked about, rather than hallucinating a column.

---

## Architecture

The agent is built as an explicit **LangGraph state machine** — not a black-box LangChain agent. This was a deliberate choice: a standard agent lets the LLM decide its own control flow, which makes it hard to *guarantee* safety behavior. LangGraph makes every transition a code-defined edge, so validation and rejection logic can never be skipped or "talked around" by the model.

```
classify_intent
   ├─ in_scope        → generate_sql → validate_sql
   ├─ out_of_scope     → reject → END
   └─ write_operation  → reject → END

validate_sql
   ├─ valid                       → execute_sql → format_response → END
   ├─ NO_QUERY (terminal)          → END
   ├─ invalid, retries remaining   → repair_sql → validate_sql   (loop)
   └─ invalid, retries exhausted   → give_up → END
```

This diagram is not hand-drawn — it's generated directly from the compiled graph object:
```python
compiled_graph.get_graph().draw_mermaid()
```
See `docs/architecture_diagram.png` for the rendered version.

### Node responsibilities

| Node | Type | Job |
|---|---|---|
| `classify_intent` | LLM call | Categorizes the message: `in_scope` / `out_of_scope` / `write_operation` |
| `reject` | Deterministic | Returns a polite rejection message, no SQL ever generated |
| `generate_sql` | LLM call | Produces SQL grounded in the live schema description + few-shot examples + chat history |
| `validate_sql` | Deterministic (`sqlglot`) | Parses the SQL as an AST; checks statement type, table/column existence, blocks multi-statement injection |
| `repair_sql` | LLM call | Given the exact validation error, attempts a corrected query (capped at 2 retries) |
| `execute_sql` | Deterministic | Runs the query against a **read-only** SQLite connection |
| `format_response` | LLM call | Converts raw rows into a natural-language answer |
| `give_up` | Deterministic | Graceful failure message after retries are exhausted |

### Defense in depth

Four independent safety layers, so no single point of failure controls whether an unsafe query can run:

1. **Intent classification** (LLM) — filters out-of-scope/destructive requests before SQL is even generated
2. **Prompt constraints** — schema-grounded generation, explicit SELECT-only instruction, `NO_QUERY:` convention for genuinely unanswerable questions
3. **`sqlglot` validation** (deterministic code, not another LLM call) — blocks non-SELECT statements, catches SQL-injection-style multi-statement payloads, verifies every referenced table/column exists in the real schema (with alias-awareness, so query-defined aliases like `AS total_spend` aren't flagged as hallucinated columns)
4. **Read-only DB connection** — SQLite opened with `mode=ro`; even if every layer above somehow failed, the OS-level connection physically cannot write

### Conversation memory

LangGraph itself is stateless between `.invoke()` calls — each graph run is a fresh execution. Multi-turn memory is implemented at the API layer instead:

- FastAPI keeps an in-memory `SESSIONS` dict, keyed by `session_id`
- On each request, prior history is looked up and passed into the graph's initial state
- History is formatted as plain text and injected into the SQL-generation prompt
- After the graph finishes, the new turn is appended and saved back
- `POST /reset/{session_id}` clears a session's history for a fresh start

**Known limitation:** session history lives in process memory, so it's lost on a service restart (e.g. Render's free-tier idle spin-down) and wouldn't survive across multiple server instances. Production fix: move to Redis or another external store.

---

## Database Schema

SQLite, 4 tables, seeded with ~60 customers / 40 products / 250 orders / ~640 order items via `Faker`.

```
customers(customer_id PK, full_name, email, country, signup_date, loyalty_tier)
products(product_id PK, product_name, category, unit_price, stock_qty, is_discontinued)
orders(order_id PK, customer_id FK, order_date, status, shipping_country)
order_items(order_item_id PK, order_id FK, product_id FK, quantity, price_at_purchase)
```

A few columns were added deliberately to stress-test the agent's precision:

- **`loyalty_tier`** — a non-obvious filter column, tests whether the agent discovers it from schema rather than assuming
- **`is_discontinued`** — tests interpreting implied intent (e.g. "available products" → `is_discontinued = 0`)
- **`shipping_country` vs. `customers.country`** — two similarly-named columns with different meanings; tests correct disambiguation
- **`price_at_purchase` vs. `products.unit_price`** — historical price paid vs. current catalog price; tests semantic precision, not just column-name matching

---

## Prompts Used

All prompts live in `app/prompts.py`. Summary of each:

| Prompt | Purpose |
|---|---|
| `INTENT_CLASSIFICATION_PROMPT` | Classifies each message into `in_scope` / `out_of_scope` / `write_operation`, returns strict JSON |
| `SQL_GENERATION_PROMPT` | Injects the live schema + few-shot examples + chat history; instructs SELECT-only output and a `NO_QUERY:` fallback when the schema genuinely lacks the requested data |
| `SQL_REPAIR_PROMPT` | Given the failed SQL and the exact validator error, asks the model to self-correct rather than regenerate blind |
| `ANSWER_FORMATTING_PROMPT` | Converts raw query result rows into a short natural-language answer |

The schema text injected into prompts is never hardcoded — it's generated live from SQLite's own `PRAGMA table_info(...)` metadata (`app/db.py::get_schema_description`), so prompts can never drift out of sync with the actual database.

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Orchestration | **LangGraph** | Explicit state graph, not a black-box agent loop — safety logic is enforced by graph structure, not prompt discipline |
| LLM | **Llama 3.3 70B via Groq** | Fast, reliable free tier (Google AI Studio's free tier returned a hard 0-quota error during development) |
| Validation | **sqlglot** | Deterministic SQL parsing — checks syntax, statement type, and schema references without relying on another LLM call |
| Backend | **FastAPI** | `/chat` endpoint with per-session conversation memory |
| Frontend | **Streamlit** | Lightweight chat UI, calls the backend over HTTP |
| Database | **SQLite** | Zero-setup, file-based — ships as part of the repo, no separate infra to provision |
| Backend hosting | **Render** | Free-tier web service |
| Frontend hosting | **Streamlit Community Cloud** | Free-tier app hosting |

---

## Project Structure

```
sql-agent/
├── schema.sql              # Table definitions
├── seed.py                 # Faker-based data generator
├── ecommerce.db             # Seeded SQLite database
├── main.py                  # FastAPI app (/chat, /reset, /health)
├── streamlit_app.py          # Chat UI
├── requirements.txt
├── runtime.txt               # Pins Python 3.11 for deployment
├── .env.example
├── test_llm_connection.py    # Standalone LLM connectivity check
├── test_nodes.py              # Node-level smoke tests
├── docs/
│   └── architecture_diagram.png
└── app/
    ├── __init__.py
    ├── db.py                  # Schema introspection + safe query execution
    ├── state.py                # AgentState (TypedDict) shared across all nodes
    ├── prompts.py               # All prompt templates
    ├── validator.py              # sqlglot-based SQL validation
    ├── nodes.py                   # Node functions (classify, generate, validate, repair, execute, respond)
    └── graph.py                   # LangGraph StateGraph wiring + conditional routing
```

---

## Setup Instructions

### Prerequisites
- Python 3.11+ (see `runtime.txt`)
- A free [Groq API key](https://console.groq.com/keys)

### 1. Clone and install

```bash
git clone https://github.com/anuragpandey991/sql-agent.git
cd sql-agent
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
```
Edit `.env` and add your key:
```
GROQ_API_KEY=your_actual_groq_key_here
```

### 3. Verify the database

The seeded database (`ecommerce.db`) ships with the repo. To regenerate it from scratch:
```bash
python -c "import sqlite3; sqlite3.connect('ecommerce.db').executescript(open('schema.sql').read())"
python seed.py
```

### 4. Verify LLM connectivity (optional but recommended)

```bash
python test_llm_connection.py
```
Expected: `✅ Success -- your API key works and the model is reachable.`

### 5. Run the backend

```bash
uvicorn main:app --reload
```
Visit `http://localhost:8000/docs` to test the `/chat` endpoint interactively.

### 6. Run the frontend (in a second terminal)

```bash
streamlit run streamlit_app.py
```
Visit `http://localhost:8501`.

### 7. (Optional) Run node-level tests

```bash
python test_nodes.py
```
Runs 5 smoke tests: happy path, out-of-scope rejection, write-operation rejection, schema-hallucination handling, and multi-turn context resolution.

---

## Example Interactions

**Standard query:**
> "Show me the top 5 customers by total spend"
→ Correct JOIN across `customers`, `orders`, `order_items`, with aggregation and ranking.

**Follow-up (context-aware):**
> "Now only from Germany"
→ Reuses the prior ranking logic and adds a country filter, without repeating the original question.

**Out-of-scope:**
> "What's the weather like today?"
→ Politely declined, no SQL attempted.

**Write operation:**
> "Delete all orders from customers in India"
→ Rejected before generation — the agent is read-only by design.

**Schema-hallucination trap:**
> "What discount did each customer get?"
→ The model recognizes no `discount` column exists and responds with `NO_QUERY:`, rather than fabricating one.

---

## Deployment Notes

- **Backend (Render):** Build command `pip install -r requirements.txt`; start command `python -m uvicorn main:app --host 0.0.0.0 --port $PORT`. `GROQ_API_KEY` set as an environment variable in the Render dashboard.
- **Frontend (Streamlit Cloud):** Deployed from `streamlit_app.py`; backend URL supplied via an `API_URL` secret in Streamlit Cloud settings (falls back to `http://localhost:8000` for local development).

---

## Known Limitations & Future Improvements

- **Session memory is in-process** — doesn't survive server restarts or scale across multiple instances. Would move to Redis for production.
- **No systematic accuracy eval** — validation is currently tested via targeted smoke cases (`test_nodes.py`), not a broader labeled question/expected-SQL dataset.
- **No streaming responses** — the full answer is returned in one response rather than streamed token-by-token.
- **No per-session rate limiting** — would add this before any production exposure.
- **Free-tier hosting cold starts** — Render's free tier sleeps after inactivity; a paid tier or a scheduled keep-alive ping would remove the wake-up delay.

---

## Author

Anurag Pandey — built for the Forward Deployed Engineer technical assignment.
