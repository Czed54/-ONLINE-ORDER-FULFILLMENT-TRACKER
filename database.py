"""database.py - SQLite connection, table creation and all SQL operations
(every query is parameterized).

Online Order Fulfillment Tracker - DSA 214 Final Laboratory Activity (Scenario 14).
"""

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from functions import (hash_password, order_stage, route_stops)


@dataclass
class Customer:
    """A registered customer of the order fulfillment system."""
    name: str
    email: str
    city: str
    phone: str = ""
    password_hash: str = ""

DB_PATH = Path(os.environ.get("ORDER_DB_PATH")
               or Path(__file__).resolve().parent / "DATABASE.db")

DEFAULT_ADMIN_USER = "admin"

DEFAULT_ADMIN_PASSWORD = "admin123"  # change it with the "Change admin password" menu option

SHIPPING_STATUSES = ["Pending", "Processing", "Shipped", "Delivered", "Cancelled"]

PAYMENT_STATUSES = ["Unpaid", "Paid", "Refunded"]

def _sql_list(values):
    """Turn a list of constants into a SQL list, e.g. ('A', 'B'). Constants only."""
    return "(" + ", ".join(f"'{v}'" for v in values) + ")"

def get_connection(db_path=DB_PATH):
    """Open (and create if needed) the SQLite database with foreign keys enabled."""
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def create_tables(conn):
    """Create the related tables if they do not exist yet (and upgrade old databases)."""
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS customers (
            customer_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            email        TEXT NOT NULL UNIQUE,
            city         TEXT NOT NULL,
            phone        TEXT NOT NULL DEFAULT '',
            password_hash TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS admins (
            admin_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            username      TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS orders (
            order_id        INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id     INTEGER NOT NULL,
            order_date      TEXT NOT NULL,
            shipping_status TEXT NOT NULL DEFAULT 'Pending'
                CHECK (shipping_status IN {_sql_list(SHIPPING_STATUSES)}),
            payment_status  TEXT NOT NULL DEFAULT 'Unpaid'
                CHECK (payment_status IN {_sql_list(PAYMENT_STATUSES)}),
            shipped_date    TEXT,
            delivered_date  TEXT,
            route_stage     INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
                ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS order_status_history (
            history_id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id   INTEGER NOT NULL,
            event      TEXT NOT NULL,
            changed_at TEXT NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (order_id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS order_items (
            item_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id     INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            quantity     INTEGER NOT NULL CHECK (quantity > 0),
            unit_price   REAL NOT NULL CHECK (unit_price >= 0),
            FOREIGN KEY (order_id) REFERENCES orders (order_id)
                ON DELETE CASCADE
        );
    """)
    # Upgrade older databases (existing data is kept).
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(orders)")}
    if "route_stage" not in columns:
        conn.execute("ALTER TABLE orders ADD COLUMN route_stage INTEGER NOT NULL DEFAULT 0")
        conn.execute("UPDATE orders SET route_stage = 1 WHERE shipping_status = 'Shipped'")
        conn.execute("UPDATE orders SET route_stage = 4 WHERE shipping_status = 'Delivered'")
    customer_columns = {row["name"] for row in conn.execute("PRAGMA table_info(customers)")}
    if "phone" not in customer_columns:
        conn.execute("ALTER TABLE customers ADD COLUMN phone TEXT NOT NULL DEFAULT ''")
    if "password_hash" not in customer_columns:
        conn.execute("ALTER TABLE customers ADD COLUMN password_hash TEXT NOT NULL DEFAULT ''")
    # First run: create the default administrator account.
    if conn.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0:
        conn.execute("INSERT INTO admins (username, password_hash) VALUES (?, ?)",
                     (DEFAULT_ADMIN_USER, hash_password(DEFAULT_ADMIN_PASSWORD)))
    conn.commit()

def _now():
    """Current local time as 'YYYY-MM-DD HH:MM' (used to stamp tracking events)."""
    return datetime.now().strftime("%Y-%m-%d %H:%M")

def _log_event(conn, order_id, event, changed_at=None):
    """Append one tracking event to an order's history (call inside a transaction)."""
    conn.execute(
        "INSERT INTO order_status_history (order_id, event, changed_at) VALUES (?, ?, ?)",
        (order_id, event, changed_at or _now()),
    )

def add_customer(conn, customer):
    """Insert a customer and return the new customer_id.

    Raises sqlite3.IntegrityError if the email already exists.
    """
    with conn:
        cur = conn.execute(
            "INSERT INTO customers (name, email, city, phone, password_hash) VALUES (?, ?, ?, ?, ?)",
            (customer.name, customer.email, customer.city, customer.phone,
             customer.password_hash),
        )
    return cur.lastrowid

def get_customers(conn):
    """Return all customers with how many orders each has placed."""
    return conn.execute("""
        SELECT c.customer_id, c.name, c.email, c.city, c.phone,
               COUNT(o.order_id) AS order_count
        FROM customers c
        LEFT JOIN orders o ON o.customer_id = c.customer_id
        GROUP BY c.customer_id
        ORDER BY c.customer_id
    """).fetchall()

def get_customer_by_email(conn, email):
    """Return the customer row with this email, or None."""
    return conn.execute("SELECT * FROM customers WHERE email = ?", (email,)).fetchone()

def set_customer_password(conn, customer_id, password):
    """Store a new (hashed) password for a customer."""
    with conn:
        conn.execute("UPDATE customers SET password_hash = ? WHERE customer_id = ?",
                     (hash_password(password), customer_id))

def get_admin(conn, username):
    """Return the admin row with this username, or None."""
    return conn.execute("SELECT * FROM admins WHERE username = ?", (username,)).fetchone()

def set_admin_password(conn, admin_id, password):
    """Store a new (hashed) password for an admin."""
    with conn:
        conn.execute("UPDATE admins SET password_hash = ? WHERE admin_id = ?",
                     (hash_password(password), admin_id))

def customer_exists(conn, customer_id):
    """Return True if the customer_id exists."""
    row = conn.execute(
        "SELECT 1 FROM customers WHERE customer_id = ?", (customer_id,)
    ).fetchone()
    return row is not None

def add_order(conn, customer_id, order_date, items, payment_status="Unpaid",
              shipping_status="Pending", shipped_date=None, delivered_date=None):
    """Insert an order and its items in one transaction; return the order_id.

    ``items`` is a list of (product_name, quantity, unit_price) tuples.
    """
    stage = {"Shipped": 1, "Delivered": 4}.get(shipping_status, 0)
    with conn:  # commits on success, rolls back on error
        cur = conn.execute(
            """INSERT INTO orders (customer_id, order_date, shipping_status,
                                   payment_status, shipped_date, delivered_date, route_stage)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (customer_id, order_date, shipping_status, payment_status,
             shipped_date, delivered_date, stage),
        )
        order_id = cur.lastrowid
        conn.executemany(
            """INSERT INTO order_items (order_id, product_name, quantity, unit_price)
               VALUES (?, ?, ?, ?)""",
            [(order_id, name, qty, price) for name, qty, price in items],
        )
        # Tracking history: what has happened to this order so far.
        placed_at = _now() if order_date == date.today().isoformat() else order_date
        _log_event(conn, order_id, "Order placed", placed_at)
        if payment_status != "Unpaid":
            _log_event(conn, order_id, f"Payment: {payment_status}", placed_at)
        if shipping_status == "Cancelled":
            _log_event(conn, order_id, "Shipping: Cancelled", placed_at)
        if shipping_status in ("Processing", "Shipped", "Delivered"):
            _log_event(conn, order_id, "Shipping: Processing", placed_at)
        if shipping_status in ("Shipped", "Delivered"):
            _log_event(conn, order_id, "Shipping: Shipped", shipped_date or placed_at)
        if shipping_status == "Delivered":
            _log_event(conn, order_id, "Shipping: Delivered", delivered_date or placed_at)
    return order_id

def get_orders(conn, order_id=None, customer_keyword=None, shipping_status=None,
               payment_status=None, date_from=None, date_to=None, customer_id=None):
    """Return orders (with customer name, city and computed total), newest first.

    Every argument is an optional filter; all given filters must match.
    """
    clauses, params = [], []
    if order_id is not None:
        clauses.append("o.order_id = ?")
        params.append(order_id)
    if customer_id is not None:
        clauses.append("o.customer_id = ?")
        params.append(customer_id)
    if customer_keyword:
        clauses.append("c.name LIKE ?")
        params.append(f"%{customer_keyword}%")
    if shipping_status:
        clauses.append("o.shipping_status = ?")
        params.append(shipping_status)
    if payment_status:
        clauses.append("o.payment_status = ?")
        params.append(payment_status)
    if date_from:
        clauses.append("o.order_date >= ?")
        params.append(date_from)
    if date_to:
        clauses.append("o.order_date <= ?")
        params.append(date_to)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    # `where` only ever contains the fixed clauses above; values stay in params.
    query = f"""
        SELECT o.order_id, c.name AS customer, c.city AS city, c.phone AS phone,
               o.order_date, o.shipping_status, o.payment_status,
               COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS total,
               o.shipped_date, o.delivered_date, o.route_stage,
               COALESCE(SUM(oi.quantity), 0) AS item_count
        FROM orders o
        JOIN customers c ON c.customer_id = o.customer_id
        LEFT JOIN order_items oi ON oi.order_id = o.order_id
        {where}
        GROUP BY o.order_id
        ORDER BY o.order_date DESC, o.order_id DESC
    """
    return conn.execute(query, params).fetchall()

def get_order_items(conn, order_id):
    """Return the line items of one order."""
    return conn.execute(
        """SELECT item_id, product_name, quantity, unit_price,
                  quantity * unit_price AS line_total
           FROM order_items WHERE order_id = ? ORDER BY item_id""",
        (order_id,),
    ).fetchall()

def get_status_history(conn, order_id):
    """Return an order's tracking events, oldest first."""
    return conn.execute(
        """SELECT event, changed_at FROM order_status_history
           WHERE order_id = ? ORDER BY changed_at, history_id""",
        (order_id,),
    ).fetchall()

def update_order_status(conn, order_id, shipping_status=None, payment_status=None):
    """Update shipping and/or payment status. Return False if the order is missing.

    Shipped/delivered dates and the parcel's map position are maintained
    automatically from the new status.
    """
    if conn.execute("SELECT 1 FROM orders WHERE order_id = ?", (order_id,)).fetchone() is None:
        return False
    today = date.today().isoformat()
    with conn:
        if shipping_status:
            conn.execute("UPDATE orders SET shipping_status = ? WHERE order_id = ?",
                         (shipping_status, order_id))
            _log_event(conn, order_id, f"Shipping: {shipping_status}")
            if shipping_status == "Shipped":
                conn.execute(
                    """UPDATE orders SET shipped_date = COALESCE(shipped_date, ?),
                       delivered_date = NULL, route_stage = MAX(route_stage, 1)
                       WHERE order_id = ?""", (today, order_id))
            elif shipping_status == "Delivered":
                conn.execute(
                    """UPDATE orders SET shipped_date = COALESCE(shipped_date, ?),
                       delivered_date = COALESCE(delivered_date, ?), route_stage = 4
                       WHERE order_id = ?""", (today, today, order_id))
            elif shipping_status in ("Pending", "Processing"):
                conn.execute(
                    """UPDATE orders SET shipped_date = NULL, delivered_date = NULL,
                       route_stage = 0 WHERE order_id = ?""", (order_id,))
        if payment_status:
            conn.execute("UPDATE orders SET payment_status = ? WHERE order_id = ?",
                         (payment_status, order_id))
            _log_event(conn, order_id, f"Payment: {payment_status}")

    return True

def confirm_order(conn, order_id):
    """Confirm a Pending order: it moves to Processing and the history is logged.

    Return False if the order is missing or is not Pending.
    """
    row = conn.execute("SELECT shipping_status FROM orders WHERE order_id = ?",
                       (order_id,)).fetchone()
    if row is None or row["shipping_status"] != "Pending":
        return False
    update_order_status(conn, order_id, shipping_status="Processing")
    with conn:
        _log_event(conn, order_id, "Order confirmed")
    return True

def advance_parcel(conn, order_id):
    """Move a Shipped parcel to the next stop on its route; return the new stop name.

    Returns None if the order is missing, is not Shipped, or is already out for delivery
    (the last step, Delivered, is done through the shipping status).
    """
    rows = get_orders(conn, order_id=order_id)
    if not rows:
        return None
    order = rows[0]
    stage = order_stage(order)
    if order["shipping_status"] != "Shipped" or stage is None or stage >= 3:
        return None
    new_stage = stage + 1
    title = route_stops(order["city"])[new_stage][0]
    with conn:
        conn.execute("UPDATE orders SET route_stage = ? WHERE order_id = ?",
                     (new_stage, order_id))
        _log_event(conn, order_id, f"Location: {title}")
    return title

def update_item_quantity(conn, order_id, item_id, quantity):
    """Change an item's quantity. Return False if the item is not in that order."""
    with conn:
        cur = conn.execute(
            "UPDATE order_items SET quantity = ? WHERE item_id = ? AND order_id = ?",
            (quantity, item_id, order_id),
        )
    return cur.rowcount > 0

def delete_order(conn, order_id):
    """Delete an order (its items are removed by ON DELETE CASCADE)."""
    with conn:
        cur = conn.execute("DELETE FROM orders WHERE order_id = ?", (order_id,))
    return cur.rowcount > 0

def get_quick_stats(conn):
    """Return headline counts shown on the main menu."""
    return conn.execute("""
        SELECT (SELECT COUNT(*) FROM customers) AS customers,
               COUNT(*) AS orders,
               COALESCE(SUM(shipping_status IN ('Pending', 'Processing')), 0) AS to_ship,
               COALESCE(SUM(shipping_status = 'Shipped'), 0) AS in_transit,
               COALESCE(SUM(payment_status = 'Unpaid'
                            AND shipping_status != 'Cancelled'), 0) AS unpaid
        FROM orders
    """).fetchone()

ORDER_TOTALS = """
    SELECT o.order_id, o.order_date, o.shipping_status, o.payment_status,
           SUM(oi.quantity * oi.unit_price) AS total
    FROM orders o
    JOIN order_items oi ON oi.order_id = o.order_id
    GROUP BY o.order_id
"""

def shipping_summary(conn):
    """Orders and value per shipping status (all statuses, in workflow order)."""
    found = {row["shipping_status"]: row for row in conn.execute(f"""
        SELECT shipping_status, COUNT(*) AS orders, SUM(total) AS amount
        FROM ({ORDER_TOTALS}) AS t GROUP BY shipping_status""")}
    return [(s, found[s]["orders"] if s in found else 0,
             found[s]["amount"] if s in found else 0.0) for s in SHIPPING_STATUSES]

def payment_summary(conn):
    """Orders and value per payment status (cancelled orders excluded, except refunds)."""
    found = {row["payment_status"]: row for row in conn.execute(f"""
        SELECT payment_status, COUNT(*) AS orders, SUM(total) AS amount
        FROM ({ORDER_TOTALS}) AS t
        WHERE shipping_status != 'Cancelled' OR payment_status = 'Refunded'
        GROUP BY payment_status""")}
    return [(s, found[s]["orders"] if s in found else 0,
             found[s]["amount"] if s in found else 0.0) for s in PAYMENT_STATUSES]

def customer_totals(conn):
    """Per-customer orders, items, order value, amount paid and amount unpaid."""
    return conn.execute("""
        SELECT c.name,
               COUNT(t.order_id) AS orders,
               SUM(t.items) AS items,
               SUM(CASE WHEN t.shipping_status != 'Cancelled' THEN t.total ELSE 0 END) AS total,
               SUM(CASE WHEN t.payment_status = 'Paid' THEN t.total ELSE 0 END) AS paid,
               SUM(CASE WHEN t.payment_status = 'Unpaid'
                         AND t.shipping_status != 'Cancelled' THEN t.total ELSE 0 END) AS unpaid
        FROM customers c
        JOIN (SELECT o.order_id, o.customer_id, o.shipping_status, o.payment_status,
                     SUM(oi.quantity) AS items, SUM(oi.quantity * oi.unit_price) AS total
              FROM orders o JOIN order_items oi ON oi.order_id = o.order_id
              GROUP BY o.order_id) AS t ON t.customer_id = c.customer_id
        GROUP BY c.customer_id
        ORDER BY total DESC, c.name
    """).fetchall()
