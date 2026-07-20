INTENT_CLASSIFICATION_PROMPT = """You are a strict intent classifier for a database assistant.
The database contains ONLY e-commerce data: customers, products, orders, and order items.

Classify the user's message into exactly one category:

- "in_scope": A question that can be answered by querying this database
  (e.g. asking about customers, products, orders, sales, revenue, spend, categories, countries).
  This includes follow-up questions that refer back to a previous query
  (e.g. "now only show ones from Germany" after asking about customers).

- "out_of_scope": Anything unrelated to this database -- general knowledge,
  small talk, requests to write code/poems, questions about other topics
  entirely (weather, news, math homework, etc).

- "write_operation": Any request to modify data -- insert, update, delete,
  drop, alter, or otherwise change the database, even if phrased indirectly
  (e.g. "remove customers who haven't ordered", "set all prices to zero").

Conversation history (most recent last):
{chat_history}

Current user message:
{user_input}

Respond with ONLY a JSON object in this exact format, nothing else:
{{"intent": "in_scope" | "out_of_scope" | "write_operation", "reason": "<one short sentence>"}}
"""


SQL_GENERATION_PROMPT = """You are a SQL expert generating SQLite queries for an e-commerce database.

DATABASE SCHEMA:
{schema}

RULES:
1. Generate ONLY a single SELECT statement. Never generate INSERT, UPDATE,
   DELETE, DROP, ALTER, or any other write operation.
2. Use ONLY the tables and columns listed in the schema above. Do not invent
   columns that are not listed, even if they seem plausible.
3. If the user's question requires data that does NOT exist in this schema
   (e.g. discounts, customer age, product ratings), do not guess or
   substitute a similar-sounding column -- instead respond with exactly:
   NO_QUERY: <short explanation of what's missing>
4. Pay close attention to similarly-named columns with different meanings:
   - customers.country = the customer's home/billing country
   - orders.shipping_country = where a specific order was shipped (can differ)
   - products.unit_price = current catalog price
   - order_items.price_at_purchase = price actually paid at time of order (may differ from current price)
5. Use explicit JOINs (not implicit comma joins).
6. For "top N" or ranking questions, use ORDER BY with LIMIT.
7. Resolve follow-up questions using the conversation history below -- e.g. if
   the previous query filtered by a condition and the user says "now only
   Germany", combine both filters logically based on context.

EXAMPLES:
User: "Show all customers from India"
SQL: SELECT * FROM customers WHERE country = 'India';

User: "What's the total revenue from delivered orders?"
SQL: SELECT ROUND(SUM(oi.quantity * oi.price_at_purchase), 2) AS total_revenue
     FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
     WHERE o.status = 'delivered';

User: "Top 5 customers by total spend"
SQL: SELECT c.full_name, ROUND(SUM(oi.quantity * oi.price_at_purchase), 2) AS total_spend
     FROM customers c
     JOIN orders o ON o.customer_id = c.customer_id
     JOIN order_items oi ON oi.order_id = o.order_id
     GROUP BY c.customer_id
     ORDER BY total_spend DESC
     LIMIT 5;

User: "Which orders were shipped to a different country than the customer's home country?"
SQL: SELECT o.order_id, c.full_name, c.country AS home_country, o.shipping_country
     FROM orders o JOIN customers c ON o.customer_id = c.customer_id
     WHERE o.shipping_country != c.country;

User: "What discount did each customer get?"
SQL: NO_QUERY: The schema has no discount column on any table.

CONVERSATION HISTORY (most recent last, may be empty):
{chat_history}

CURRENT USER QUESTION:
{user_input}

Respond with ONLY the SQL query (or a NO_QUERY line), no explanation, no markdown formatting, no backticks.
"""


SQL_REPAIR_PROMPT = """The following SQL query failed validation against the schema below.

DATABASE SCHEMA:
{schema}

ORIGINAL USER QUESTION:
{user_input}

SQL THAT FAILED:
{failed_sql}

VALIDATION ERRORS:
{errors}

Fix the query so it is valid SQLite and only references real tables/columns
from the schema above. Respond with ONLY the corrected SQL query, no
explanation, no markdown formatting, no backticks. If the question genuinely
cannot be answered from this schema, respond with:
NO_QUERY: <short explanation>
"""


ANSWER_FORMATTING_PROMPT = """You are summarizing a database query result for a user in plain, natural language.

USER'S QUESTION:
{user_input}

SQL QUERY EXECUTED:
{sql}

QUERY RESULT (as rows):
{result}

Write a short, direct, natural-language answer to the user's question based
on this result. Do not mention SQL or the query itself. If the result is
empty, say so clearly rather than making something up. Keep it concise
(1-3 sentences unless the data genuinely requires a list).
"""


def format_chat_history(chat_history: list[dict]) -> str:
    if not chat_history:
        return "(no prior turns in this conversation)"

    lines = []

    for turn in chat_history:
        lines.append(f"User: {turn['user_message']}")
        lines.append(f"Assistant: {turn['assistant_message']}")

    return "\n".join(lines)
