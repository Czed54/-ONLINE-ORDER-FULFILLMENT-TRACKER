"""
Laboratory Activity 7
Online Order Fulfillment Tracker
Database Design, SQL, and Python Integration
"""

import sqlite3
from pathlib import Path

DB_PATH = Path("lab7_demo.db")


def connect_database():
    """Connect to the demonstration database and enable foreign keys."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def create_tables(conn):
    """Create three related tables with primary and foreign keys."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE
        );

        CREATE TABLE IF NOT EXISTS orders (
            order_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            order_date TEXT NOT NULL,
            FOREIGN KEY (customer_id)
                REFERENCES customers(customer_id)
        );

        CREATE TABLE IF NOT EXISTS order_items (
            item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity > 0),
            unit_price REAL NOT NULL CHECK(unit_price >= 0),
            FOREIGN KEY (order_id)
                REFERENCES orders(order_id)
        );
    """)
    conn.commit()


def insert_sample_data(conn):
    """Insert sample customers, orders, and order items."""
    with conn:
        conn.execute(
            "INSERT INTO customers (name, email) VALUES (?, ?)",
            ("Maria Santos", "maria@example.com")
        )
        conn.execute(
            "INSERT INTO customers (name, email) VALUES (?, ?)",
            ("Juan Reyes", "juan@example.com")
        )
        conn.execute(
            "INSERT INTO customers (name, email) VALUES (?, ?)",
            ("Ana Cruz", "ana@example.com")
        )

        conn.execute(
            "INSERT INTO orders (customer_id, order_date) VALUES (?, ?)",
            (1, "2026-11-16")
        )
        conn.execute(
            "INSERT INTO orders (customer_id, order_date) VALUES (?, ?)",
            (2, "2026-11-16")
        )
        conn.execute(
            "INSERT INTO orders (customer_id, order_date) VALUES (?, ?)",
            (3, "2026-11-16")
        )

        conn.executemany(
            """INSERT INTO order_items
               (order_id, product_name, quantity, unit_price)
               VALUES (?, ?, ?, ?)""",
            [
                (1, "Notebook", 2, 50.00),
                (1, "Ballpen", 3, 15.00),
                (2, "Folder", 5, 12.00),
                (3, "Eraser", 4, 5.00),
                (3, "Ruler", 2, 10.00)
            ]
        )


def retrieve_orders(conn):
    """Retrieve orders and customer names using an INNER JOIN."""
    query = """
        SELECT
            orders.order_id,
            customers.name AS customer_name,
            orders.order_date,
            order_items.product_name,
            order_items.quantity,
            order_items.unit_price
        FROM orders
        INNER JOIN customers
            ON orders.customer_id = customers.customer_id
        INNER JOIN order_items
            ON orders.order_id = order_items.order_id
        ORDER BY orders.order_id
    """
    return conn.execute(query).fetchall()



def search_customer(conn, search_term):
    """Search for customers by name using a parameterized query."""
    query = """
        SELECT customer_id, name, email
        FROM customers
        WHERE name LIKE ?
        ORDER BY name
    """
    return conn.execute(query, (f"%{search_term}%",)).fetchall()


def update_order_item(conn, item_id, new_quantity):
    """Update an order item's quantity and return whether it succeeded."""
    if not isinstance(new_quantity, int) or isinstance(new_quantity, bool):
        raise ValueError("Quantity must be an integer.")

    if new_quantity <= 0:
        raise ValueError("Quantity must be positive.")

    with conn:
        cursor = conn.execute(
            "UPDATE order_items SET quantity = ? WHERE item_id = ?",
            (new_quantity, item_id)
        )

    return cursor.rowcount > 0


def main():
    """Run the database demonstration and display SQL operation results."""
    # Recreate a clean demonstration database on every run.
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = connect_database()

    try:
        print("ONLINE ORDER FULFILLMENT TRACKER")
        print("LABORATORY ACTIVITY 7 DEMONSTRATION")

        create_tables(conn)
        insert_sample_data(conn)

        print("\nTEST 1 - INSERT")
        print("Inserted 3 customers, 3 orders, and 5 order items.")
        print("PASS - Sample records inserted.")

        print("\nTEST 2 - SELECT WITH INNER JOIN")
        for row in retrieve_orders(conn):
            print(
                f"Order #{row['order_id']} | "
                f"{row['customer_name']} | "
                f"{row['product_name']} | "
                f"Qty: {row['quantity']} | "
                f"PHP {row['unit_price']:.2f}"
            )

        print("\nTEST 3 - SEARCH CUSTOMER")
        results = search_customer(conn, "Maria")
        for customer in results:
            print(
                f"Found: {customer['name']} | "
                f"Email: {customer['email']}"
            )
        print("PASS - Customer search completed.")

        print("\nTEST 4 - UPDATE")
        success = update_order_item(conn, 1, 5)
        print("Updated item quantity:", success)

        updated = conn.execute(
            "SELECT quantity FROM order_items WHERE item_id = ?",
            (1,)
        ).fetchone()

        print("New quantity:", updated["quantity"])

        print("\nTotal records:")
        for table in ("customers", "orders", "order_items"):
            count = conn.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            print(f"{table}: {count}")

        print("\nAll database operations completed.")

    finally:
        conn.close()
        print("Database connection closed.")


if __name__ == "__main__":
    main()
