import sqlite3
import random
from datetime import timedelta, datetime, date
from faker import Faker

DB_PATH = "ecommerce.db"
SCHEMA_PATH = "schema.sql"

sqlite3.register_adapter(date, lambda d: d.isoformat())

fake = Faker()
Faker.seed(42)
random.seed(42)

N_CUSTOMERS = 60
N_PRODUCTS = 40
N_ORDERS = 250
MAX_ITEMS_PER_ORDER = 4

COUNTRIES = [
    "India",
    "United States",
    "Germany",
    "United Kingdom",
    "Canada",
    "Australia",
    "France",
    "Brazil",
    "Japan",
    "Singapore",
]

CATEGORIES = [
    "Electronics",
    "Apparel",
    "Home & Kitchen",
    "Books",
    "Sports & Outdoors",
    "Beauty",
    "Toys",
    "Groceries",
]

LOYALTY_TIERS = ["Bronze", "Silver", "Gold"]
LOYALTY_WEIGHTS = [0.5, 0.35, 0.15]

ORDER_STATUSES = ["placed", "shipped", "delivered", "cancelled"]
ORDER_STATUS_WEIGHTS = [0.15, 0.20, 0.55, 0.10]


def build_schema(conn):
    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())


def seed_customers(conn):
    rows = []
    for _ in range(N_CUSTOMERS):
        full_name = fake.name()
        email = fake.unique.email()
        country = random.choice(COUNTRIES)
        signup_date = fake.date_between(start_date="-3y", end_date="-1M")
        loyalty_tier = random.choices(LOYALTY_TIERS, weights=LOYALTY_WEIGHTS)[0]
        rows.append((full_name, email, country, signup_date, loyalty_tier))

    conn.executemany(
        """INSERT INTO customers (full_name, email, country, signup_date, loyalty_tier)
           VALUES (?, ?, ?, ?, ?)""",
        rows,
    )


def seed_products(conn):
    rows = []
    for _ in range(N_PRODUCTS):
        product_name = fake.unique.catch_phrase()
        category = random.choice(CATEGORIES)
        unit_price = round(random.uniform(5, 500), 2)
        stock_qty = random.randint(0, 500)
        is_discontinued = 1 if random.random() < 0.12 else 0
        rows.append((product_name, category, unit_price, stock_qty, is_discontinued))

    conn.executemany(
        """INSERT INTO products (product_name, category, unit_price, stock_qty, is_discontinued)
           VALUES (?, ?, ?, ?, ?)""",
        rows,
    )


def seed_orders_and_items(conn):
    cur = conn.cursor()
    cur.execute("SELECT customer_id, country, signup_date FROM customers")
    customers = cur.fetchall()

    cur.execute("SELECT product_id, unit_price FROM products")
    products = cur.fetchall()

    order_rows = []
    for _ in range(N_ORDERS):
        customer_id, home_country, signup_date = random.choice(customers)

        if isinstance(signup_date, str):
            start = datetime.strptime(signup_date, "%Y-%m-%d").date()
        else:
            start = signup_date

        if start >= date.today():
            start = date.today() - timedelta(days=1)

        order_date = fake.date_between(start_date=start, end_date="today")
        status = random.choices(ORDER_STATUSES, weights=ORDER_STATUS_WEIGHTS)[0]

        if random.random() < 0.20:
            shipping_country = random.choice(
                [c for c in COUNTRIES if c != home_country]
            )
        else:
            shipping_country = home_country

        order_rows.append((customer_id, order_date, status, shipping_country))

    cur.executemany(
        """INSERT INTO orders (customer_id, order_date, status, shipping_country)
           VALUES (?, ?, ?, ?)""",
        order_rows,
    )
    conn.commit()

    cur.execute("SELECT order_id FROM orders")
    order_ids = [row[0] for row in cur.fetchall()]

    item_rows = []
    for order_id in order_ids:
        n_items = random.randint(1, MAX_ITEMS_PER_ORDER)
        chosen_products = random.sample(products, k=min(n_items, len(products)))

        for product_id, current_price in chosen_products:
            quantity = random.randint(1, 5)
            drift = random.uniform(-0.15, 0.10)
            price_at_purchase = round(max(1.0, current_price * (1 + drift)), 2)
            item_rows.append(
                (order_id, product_id, quantity, price_at_purchase)
            )

    cur.executemany(
        """INSERT INTO order_items (order_id, product_id, quantity, price_at_purchase)
           VALUES (?, ?, ?, ?)""",
        item_rows,
    )
    conn.commit()


def main():
    conn = sqlite3.connect(DB_PATH)
    build_schema(conn)
    seed_customers(conn)
    seed_products(conn)
    conn.commit()
    seed_orders_and_items(conn)

    cur = conn.cursor()
    for table in ["customers", "products", "orders", "order_items"]:
        count = cur.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        print(f"{table}: {count} rows")

    conn.close()
    print(f"\nSeeded database created at ./{DB_PATH}")


if __name__ == "__main__":
    main()
