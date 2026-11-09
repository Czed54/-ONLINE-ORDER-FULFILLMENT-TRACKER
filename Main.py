"""Online Order Fulfillment Tracker.

DSA 214 - Final Laboratory Activity - Scenario 14.
Command-line app: track customer orders, order items, shipping statuses,
payment totals AND where each parcel is on a delivery map, using
Python + SQLite (standard library only).
"""

import getpass
import hashlib
import html
import os
import re
import secrets
import sqlite3
import urllib.parse
import webbrowser
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
# Philippine mobile number: 09XXXXXXXXX, 9XXXXXXXXX, 639XXXXXXXXX or +639XXXXXXXXX
PHONE_PATTERN = re.compile(r"^(?:\+?63|0)?9\d{9}$")

@dataclass
class Customer:
    """A registered customer of the order fulfillment system."""
    name: str
    email: str
    city: str
    phone: str = ""
    password_hash: str = ""

# Business rule: which shipping status may follow which.
ALLOWED_TRANSITIONS = {
    "Pending": ["Processing", "Cancelled"],
    "Processing": ["Shipped", "Cancelled"],
    "Shipped": ["Delivered"],
    "Delivered": [],
    "Cancelled": [],
}
EDITABLE_STATUSES = ("Pending", "Processing")  # items may only change before shipping

#  business rules
def can_transition(current, new):
    """Return True if an order may move from shipping status ``current`` to ``new``."""
    return new in ALLOWED_TRANSITIONS.get(current, [])

def allowed_next_statuses(current):
    """Return the list of shipping statuses an order may move to next."""
    return list(ALLOWED_TRANSITIONS.get(current, []))

def calculate_order_total(items):
    """Return the total of (product, quantity, unit_price) tuples."""
    return sum(quantity * price for _, quantity, price in items)

def is_valid_email(email):
    """Return True if ``email`` looks like name@domain.tld."""
    return bool(EMAIL_PATTERN.match(email))

def is_valid_name(name):
    """Return True for 2-60 characters made of letters, spaces and . ' - only."""
    cleaned = name.strip()
    return (2 <= len(cleaned) <= 60
            and any(ch.isalpha() for ch in cleaned)
            and all(ch.isalpha() or ch in " .'-" for ch in cleaned))

def is_valid_phone(phone):
    """Return True for a Philippine mobile number such as 09171234567 or +639171234567."""
    cleaned = re.sub(r"[\s-]", "", phone)
    return bool(PHONE_PATTERN.match(cleaned))

def normalize_phone(phone):
    """Return a valid mobile number in the standard 09XXXXXXXXX format."""
    cleaned = re.sub(r"[\s-]", "", phone).lstrip("+")
    return "0" + cleaned[-10:]

def hash_password(password):
    """Return 'salt$hash' for a password (PBKDF2-SHA256); the password itself is never stored."""
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}${digest.hex()}"

def verify_password(password, stored):
    """Return True if ``password`` matches a value made by hash_password()."""
    if not stored or "$" not in stored:
        return False
    salt, expected = stored.split("$", 1)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return secrets.compare_digest(digest.hex(), expected)

def paginate(rows, page, page_size=10):
    """Return (rows_on_page, page_number, total_pages); page is clamped to a valid value."""
    total_pages = max(1, -(-len(rows) // page_size))  # ceiling division
    page = min(max(page, 1), total_pages)
    start = (page - 1) * page_size
    return rows[start:start + page_size], page, total_pages

#  formatting
def format_money(amount):
    """Format a number as Philippine pesos, e.g. 'PHP 1,250.00'."""
    return f"PHP {amount:,.2f}"

def banner(title):
    """Print a plain section heading."""
    print(f"\n=== {title} ===")

def ok(message):
    """Print a success message."""
    print(f"[OK] {message}")

def warn(message):
    """Print a problem message."""
    print(f"[!] {message}")

def info(message):
    """Print a neutral notice."""
    print(f"[i] {message}")

def print_table(headers, rows):
    """Print rows (lists of values) as an aligned text table."""
    if not rows:
        print("  (no records found)")
        return
    text_rows = [[str(cell) for cell in row] for row in rows]
    widths = [max(len(h), *(len(r[i]) for r in text_rows)) for i, h in enumerate(headers)]
    header_line = "  ".join(h.ljust(w) for h, w in zip(headers, widths))
    print(header_line)
    print("-" * len(header_line))
    for row in text_rows:
        print("  ".join(cell.ljust(width) for cell, width in zip(row, widths)))


#  validated input
def read_text(prompt, required=True, max_length=100):
    """Prompt for text; keep asking while it is empty (if required) or too long."""
    while True:
        value = input(prompt).strip()
        if not value and required:
            print("  This field is required.")
        elif len(value) > max_length:
            print(f"  Please use at most {max_length} characters.")
        else:
            return value

def read_name(prompt):
    """Prompt for a person's name and validate it with is_valid_name()."""
    while True:
        value = read_text(prompt)
        if is_valid_name(value):
            return value
        print("  Names need 2-60 letters (spaces, . ' - allowed); no digits or symbols.")

def read_email(prompt):
    """Prompt for an email address; returns it lower-cased."""
    while True:
        value = read_text(prompt).lower()
        if is_valid_email(value):
            return value
        print("  Invalid email. Example: juan@example.com")

def read_phone(prompt):
    """Prompt for a mobile number; returns it as 09XXXXXXXXX."""
    while True:
        value = read_text(prompt)
        if is_valid_phone(value):
            return normalize_phone(value)
        print("  Invalid mobile number. Example: 09171234567 or +639171234567")

def read_password(prompt):
    """Prompt for a password without showing it on screen."""
    return getpass.getpass(prompt)

def read_new_password():
    """Ask for a new password (at least 6 characters) twice until both match."""
    while True:
        first = read_password("Password (at least 6 characters): ")
        if len(first) < 6:
            print("  The password must have at least 6 characters.")
            continue
        if first != read_password("Confirm password: "):
            print("  The passwords do not match.")
            continue
        return first

def read_int(prompt, minimum=None, maximum=None, allow_blank=False):
    """Prompt for a whole number within optional bounds. Blank returns None if allowed."""
    while True:
        raw = input(prompt).strip()
        if allow_blank and raw == "":
            return None
        try:
            number = int(raw)  # type conversion: str -> int
        except ValueError:
            print("  Please enter a whole number.")
            continue
        if minimum is not None and number < minimum:
            print(f"  Value must be at least {minimum}.")
        elif maximum is not None and number > maximum:
            print(f"  Value must be at most {maximum}.")
        else:
            return number

def read_float(prompt, minimum=0.0, maximum=1_000_000.0):
    """Prompt for a decimal number between ``minimum`` and ``maximum``."""
    while True:
        raw = input(prompt).strip().replace(",", "")
        try:
            number = float(raw)  # type conversion: str -> float
        except ValueError:
            print("  Please enter a number, e.g. 249.50.")
            continue
        if not minimum <= number <= maximum:
            print(f"  Value must be between {minimum:,.0f} and {maximum:,.0f}.")
        else:
            return number

def read_date(prompt, allow_blank=False, allow_future=True):
    """Prompt for a YYYY-MM-DD date. Returns an ISO string (None if blank allowed)."""
    while True:
        raw = input(prompt).strip()
        if allow_blank and raw == "":
            return None
        try:
            parsed = datetime.strptime(raw, "%Y-%m-%d").date()
        except ValueError:
            print("  Use a real date in the format YYYY-MM-DD, e.g. 2026-11-07.")
            continue
        if not allow_future and parsed > date.today():
            print("  The date cannot be in the future.")
            continue
        return parsed.isoformat()

def read_choice(title, options, allow_cancel=False):
    """Show a numbered list; return the chosen option (None if 0 = cancel is allowed)."""
    print(title)
    for number, option in enumerate(options, start=1):
        print(f"  {number}. {option}")
    if allow_cancel:
        print("  0. Cancel")
    index = read_int("Choice: ", minimum=0 if allow_cancel else 1, maximum=len(options))
    return None if index == 0 else options[index - 1]

def read_yes_no(prompt):
    """Ask a yes/no question until the answer is y/yes or n/no; return a bool."""
    while True:
        answer = input(f"{prompt} (y/n): ").strip().lower()
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("  Please answer y or n.")


# 2. DATABASE: tables and SQL operations (all parameterized)

# The program uses the project's DATABASE.db (same file as the GUI).
# ORDER_DB_PATH lets tests use a throw-away database instead of the real one.
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

#customers
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

#  orders
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

# 3. DELIVERY MAP: where is the parcel right now?

STORE_NAME = os.environ.get("STORE_NAME", "").strip() or "Store Warehouse"
STORE_PLACE = os.environ.get("STORE_CITY", "").strip()  # warehouse city for map links


def route_stops(city):
    """Return the delivery route as [(stop name, place used for map links), ...].

    Stage numbers: 0 warehouse, 1 sorting hub, 2 local hub, 3 out for delivery, 4 delivered.
    """
    origin = STORE_PLACE or city
    return [
        (STORE_NAME, origin),
        ("Sorting Hub", origin),
        (f"{city} Delivery Hub", city),
        (f"Out for delivery to {city}", city),
        (f"Delivered - {city}", city),
    ]


def order_stage(order):
    """Return the parcel's stop number (0-4) for an order row, or None if cancelled."""
    status = order["shipping_status"]
    if status == "Cancelled":
        return None
    if status == "Delivered":
        return 4
    if status == "Shipped":
        return min(max(order["route_stage"], 1), 3)
    return 0


def where_is_order(order):
    """Describe where an order is: stage, a friendly sentence and the place."""
    stage = order_stage(order)
    city = order["city"]
    if stage is None:
        return {"stage": None, "place": "-", "map_place": None,
                "headline": "This order has been cancelled and will not be delivered."}
    title, map_place = route_stops(city)[stage]
    status = order["shipping_status"]
    if status == "Pending":
        text = "We received your order and are getting it ready."
    elif status == "Processing":
        text = f"Your order is being packed at {title}."
    elif status == "Delivered":
        text = f"Your order has ARRIVED - delivered to {city}."
    elif stage == 1:
        text = "Your parcel has shipped and is now at the Sorting Hub."
    elif stage == 2:
        text = f"Your parcel arrived at the {title}."
    else:
        text = "Your order is OUT FOR DELIVERY - it will reach you very soon."
    return {"stage": stage, "place": title, "map_place": map_place, "headline": text}


def map_url(place):
    """Return a Google Maps link that searches for ``place``."""
    return "https://www.google.com/maps/search/?api=1&query=" + urllib.parse.quote(place)


def route_map_lines(order):
    """Return the delivery route as text lines with a marker on the parcel's stop."""
    stage = order_stage(order)
    if stage is None:
        return ["  Cancelled - this order will not be delivered."]
    lines = []
    stops = route_stops(order["city"])
    for index, (title, _place) in enumerate(stops):
        if index < stage or stage == 4:
            mark, tag = "[x]", ""
        elif index == stage:
            mark, tag = "[>]", "   <-- YOUR PARCEL IS HERE"
        else:
            mark, tag = "[ ]", ""
        if stage == 4 and index == 4:
            tag = "   <-- DELIVERED"
        lines.append(f"  {mark} {title}{tag}")
    return lines


def print_route_map(order):
    """Print the delivery route and a map link."""
    where = where_is_order(order)
    print("\n  DELIVERY ROUTE")
    for line in route_map_lines(order):
        print(line)
    print(f"  {where['headline']}")
    if where["map_place"]:
        print(f"  Map link: {map_url(where['map_place'])}")


def _route_rows_html(order):
    """Return the delivery route as HTML table rows (used by the browser map page)."""
    stage = order_stage(order)
    if stage is None:
        return "<tr><td>Cancelled - this order will not be delivered.</td></tr>"
    rows = []
    for index, (title, _place) in enumerate(route_stops(order["city"])):
        if index < stage or stage == 4:
            mark, note = "[x]", ""
        elif index == stage:
            mark, note = "[>]", " &lt;-- YOUR PARCEL IS HERE"
        else:
            mark, note = "[ ]", ""
        if stage == 4 and index == 4:
            note = " &lt;-- DELIVERED"
        rows.append(f"<tr><td>{mark}</td><td>{html.escape(title)}{note}</td></tr>")
    return "".join(rows)


MAP_PAGE_TEMPLATE = """<!doctype html>
<html><head><meta charset="utf-8"><title>@@TITLE@@</title></head><body>
<h1>@@TITLE@@</h1><p>@@SUB@@</p>
<p><b>@@HEADLINE@@</b></p>
<iframe src="@@EMBED@@" width="100%" height="340" loading="lazy"></iframe>
<p><a href="@@LINK@@" target="_blank">Open in Google Maps</a></p>
<h3>Delivery route</h3><table>@@ROUTE@@</table>
<h3>Items</h3><table cellpadding="4">@@ITEMS@@</table>
<p><b>Total: @@TOTAL@@</b></p>
<p>The map needs an internet connection.</p>
</body></html>
"""


def write_map_page(conn, order_id):
    """Write an HTML page with a live map of the parcel's place; return its path."""
    snap = _order_snapshot(conn, order_id)
    if snap is None:
        return None
    order, where = snap["order"], snap["where"]
    place = where["map_place"] or order["city"]
    items = "".join(
        f"<tr><td>{html.escape(i['product_name'])}</td><td>x{i['quantity']}</td>"
        f"<td align='right'>{format_money(i['line_total'])}</td></tr>" for i in snap["items"])
    values = {
        "@@TITLE@@": html.escape(f"Order #{order_id} - delivery map"),
        "@@SUB@@": html.escape(f"{order['customer']} | placed {order['order_date']}"),
        "@@HEADLINE@@": html.escape(where["headline"]),
        "@@EMBED@@": html.escape("https://maps.google.com/maps?q="
                                 + urllib.parse.quote(place) + "&z=13&output=embed", quote=True),
        "@@LINK@@": html.escape(map_url(place), quote=True),
        "@@ROUTE@@": _route_rows_html(order),
        "@@ITEMS@@": items,
        "@@TOTAL@@": format_money(order["total"]),
    }
    page = MAP_PAGE_TEMPLATE
    for token, value in values.items():
        page = page.replace(token, value)
    folder = DB_PATH.parent / "order_maps"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"order_{order_id}_map.html"
    path.write_text(page, encoding="utf-8")
    return path

# 4. ORDER SNAPSHOT (everything about one order, used by the map page)

def _order_snapshot(conn, order_id):
    """Gather the order, its items, its history and where it is right now."""
    rows = get_orders(conn, order_id=order_id)
    if not rows:
        return None
    order = rows[0]
    return {"order": order, "items": get_order_items(conn, order_id),
            "history": get_status_history(conn, order_id), "where": where_is_order(order)}


# 5. SHIPPING & PAYMENT BOARD

# One row per order with its computed total (used by several measures).
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

def print_board(conn):
    """Shipping statuses, payment totals, and per-customer totals."""
    banner("Shipping & Payment Board")
    if conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0:
        print("No orders stored yet. Register a customer and place an order first.")
        return

    print("\nShipping statuses")
    for status, orders, amount in shipping_summary(conn):
        print(f"  {status:<12} {orders:>3} order{'s' if orders != 1 else ' '}  {format_money(amount):>16}")

    print("\nPayment totals (cancelled orders excluded, except refunds)")
    payments = {s: (n, amt) for s, n, amt in payment_summary(conn)}
    for status in PAYMENT_STATUSES:
        orders, amount = payments[status]
        print(f"  {status:<12} {format_money(amount):>16}   ({orders} order{'s' if orders != 1 else ''})")
    paid, unpaid = payments["Paid"][1], payments["Unpaid"][1]
    billable = paid + unpaid
    rate = (paid / billable * 100) if billable else 0.0
    print(f"  Collection rate: {rate:.1f}% of billable value "
          f"({format_money(paid)} of {format_money(billable)})")

    print("\nCustomer totals (highest order value first)")
    print_table(["Customer", "Orders", "Items", "Order value", "Paid", "Unpaid"],
                [[r["name"], r["orders"], r["items"], format_money(r["total"]),
                  format_money(r["paid"]), format_money(r["unpaid"])]
                 for r in customer_totals(conn)])


# 6. MENU FLOWS AND PROGRAM START

def show_menu(conn):
    """Display the admin main menu with a short summary of the stored data."""
    stats = get_quick_stats(conn)
    print("\n" + "=" * 60)
    print("ONLINE ORDER FULFILLMENT TRACKER - ADMIN")
    print("=" * 60)
    print(f"Customers: {stats['customers']}   Orders: {stats['orders']}   "
          f"To ship: {stats['to_ship']}   In transit: {stats['in_transit']}   "
          f"Unpaid: {stats['unpaid']}")
    print("-" * 60)
    for key, label, _ in MENU:
        print(f"  {key:>2}. {label}")
    print("-" * 60)

def show_orders(rows):
    """Print a list of order rows as a table."""
    print_table(
        ["ID", "Customer", "Order date", "Items", "Shipping", "Payment", "Total"],
        [[r["order_id"], r["customer"], r["order_date"], r["item_count"], r["shipping_status"],
          r["payment_status"], format_money(r["total"])] for r in rows],
    )

def sign_up_flow(conn):
    """Customer sign-up: register a new account after validating every field."""
    banner("Customer Sign Up")
    name = read_name("Full name: ")
    email = read_email("Email: ")
    phone = read_phone("Mobile number (e.g. 09171234567): ")
    city = read_text("City: ", max_length=60)
    password = read_new_password()
    try:
        customer_id = add_customer(
            conn, Customer(name=name, email=email, city=city, phone=phone,
                           password_hash=hash_password(password)))
        ok(f"Account created. Your customer ID is {customer_id}.")
        return get_customer_by_email(conn, email)
    except sqlite3.IntegrityError:
        warn("A customer with that email already exists. Nothing was saved.")
        return None

def view_customers_flow(conn):
    """List all customers."""
    banner("Customers")
    rows = get_customers(conn)
    print_table(
        ["ID", "Name", "Email", "Mobile", "City", "Orders"],
        [[r["customer_id"], r["name"], r["email"], r["phone"] or "-", r["city"],
          r["order_count"]] for r in rows],
    )

def add_order_flow(conn, customer_id=None):
    """Create an order with one or more items, reviewed before saving.

    Admins pick the customer; a logged-in customer always orders for themselves.
    """
    banner("Place Order")
    if customer_id is None:
        if not get_customers(conn):
            info("No registered customers yet. Customers create their own account at the login screen.")
            return
        view_customers_flow(conn)
        customer_id = read_int("\nCustomer ID (blank to cancel): ", minimum=1, allow_blank=True)
        if customer_id is None:
            info("Cancelled.")
            return
        if not customer_exists(conn, customer_id):
            warn(f"No customer with ID {customer_id}.")
            return

    order_date = read_date("Order date (YYYY-MM-DD, blank = today): ",
                           allow_blank=True, allow_future=False)
    order_date = order_date or date.today().isoformat()

    items = []
    while True:
        product = read_text("Product name (blank to finish): ", required=False)
        if not product:
            if items:
                break
            print("  An order needs at least one item.")
            continue
        quantity = read_int("  Quantity: ", minimum=1, maximum=1000)
        price = read_float("  Unit price (PHP): ", minimum=0)
        items.append((product, quantity, price))
        print(f"  Added: {quantity} x {product} = {format_money(quantity * price)}")

    payment = read_choice("Payment status:", PAYMENT_STATUSES)

    print("\nOrder review")
    print_table(["Product", "Qty", "Unit price", "Line total"],
                [[n, q, format_money(p), format_money(q * p)] for n, q, p in items])
    print(f"Date: {order_date} | Items: {sum(q for _, q, _ in items)} | "
          f"Total: {format_money(calculate_order_total(items))}")
    if not read_yes_no("Save this order?"):
        info("Order discarded.")
        return
    order_id = add_order(conn, customer_id, order_date, items, payment_status=payment)
    ok(f"Order #{order_id} saved with status Pending. It will be confirmed by the admin.")

def confirm_order_flow(conn):
    """Confirm a Pending order so it moves to Processing."""
    banner("Confirm Order")
    pending = get_orders(conn, shipping_status="Pending")
    if not pending:
        info("There are no Pending orders to confirm.")
        return
    print("Pending orders:")
    show_orders(pending)
    order_id = read_int("\nOrder ID to confirm (blank to cancel): ", minimum=1, allow_blank=True)
    if order_id is None:
        info("Cancelled.")
        return
    rows = get_orders(conn, order_id=order_id)
    if not rows:
        warn(f"No order with ID {order_id}.")
        return
    order = rows[0]
    if order["shipping_status"] != "Pending":
        warn(f"Order #{order_id} is {order['shipping_status']}; only Pending orders can be confirmed.")
        return
    print(f"\nOrder #{order['order_id']} | {order['customer']} | Mobile: {order['phone'] or '-'}")
    print_table(["Product", "Qty", "Unit price", "Line total"],
                [[i["product_name"], i["quantity"], format_money(i["unit_price"]),
                  format_money(i["line_total"])] for i in get_order_items(conn, order_id)])
    print(f"Order total: {format_money(order['total'])} | Payment: {order['payment_status']}")
    if not read_yes_no("Confirm this order?"):
        info("Order not confirmed.")
        return
    if confirm_order(conn, order_id):
        ok(f"Order #{order_id} confirmed. Status is now Processing.")
    else:
        warn("The order could not be confirmed. Nothing was changed.")

def view_orders_flow(conn):
    """List all orders, ten per page, with next/previous navigation."""
    banner("All Orders")
    rows = get_orders(conn)
    if not rows:
        print("  (no orders found) - place an order to get started.")
        return
    page = 1
    while True:
        chunk, page, total_pages = paginate(rows, page)
        show_orders(chunk)
        print(f"\nPage {page}/{total_pages} - {len(rows)} orders in total")
        if total_pages == 1:
            break
        nav = input("[N]ext  [P]revious  [Q]uit: ").strip().lower()
        if nav in ("n", "next"):
            page += 1
        elif nav in ("p", "previous"):
            page -= 1
        elif nav in ("q", "quit", ""):
            break
        else:
            print("  Type N, P or Q.")

def order_details_flow(conn, customer_id=None):
    """Show one order with its line items (customers only see their own orders)."""
    banner("Order Details")
    order_id = read_int("Order ID: ", minimum=1)
    rows = get_orders(conn, order_id=order_id, customer_id=customer_id)
    if not rows:
        warn(f"No order with ID {order_id}.")
        return
    order = rows[0]
    print(f"Order #{order['order_id']} | {order['customer']} | {order['order_date']}")
    print(f"Mobile: {order['phone'] or '-'}")
    print(f"Shipping: {order['shipping_status']} | Payment: {order['payment_status']}")
    print(f"Shipped: {order['shipped_date'] or '-'} | Delivered: {order['delivered_date'] or '-'}")
    print_table(
        ["Item ID", "Product", "Qty", "Unit price", "Line total"],
        [[i["item_id"], i["product_name"], i["quantity"],
          format_money(i["unit_price"]), format_money(i["line_total"])]
         for i in get_order_items(conn, order_id)],
    )
    print(f"Order total: {format_money(order['total'])}")

def track_order_flow(conn, customer_id=None):
    """Show an order's progress, delivery map, items, payment total and history."""
    banner("Track Order")
    order_id = read_int("Order ID to track: ", minimum=1)
    rows = get_orders(conn, order_id=order_id, customer_id=customer_id)
    if not rows:
        warn(f"No order with ID {order_id}.")
        return
    order = rows[0]
    print(f"\n  Order #{order['order_id']}  -  {order['customer']} ({order['city']})")
    print(f"  Placed on {order['order_date']}  |  {order['item_count']} item(s)")
    print(f"  Shipping status: {order['shipping_status']}")

    print_route_map(order)

    print()
    print_table(
        ["Product", "Qty", "Unit price", "Line total"],
        [[i["product_name"], i["quantity"], format_money(i["unit_price"]),
          format_money(i["line_total"])] for i in get_order_items(conn, order_id)],
    )
    print(f"\n  Payment total: {format_money(order['total'])}"
          f"   Payment status: {order['payment_status']}")

    print("\n  Tracking history")
    history = get_status_history(conn, order_id)
    if not history:
        print("  (no tracking history was recorded for this older order)")
    for entry in history:
        print(f"  {entry['changed_at']}  {entry['event']}")

    if read_yes_no("\nOpen the live map in your web browser?"):
        path = write_map_page(conn, order_id)
        if path is not None:
            info(f"Map page saved: {path}")
            try:
                webbrowser.open(path.as_uri())
            except webbrowser.Error:
                info("Could not open the browser automatically. Open that file by hand.")

def board_flow(conn):
    """Show the shipping and payment board."""
    print_board(conn)

def search_once(conn, customer_id=None):
    """Run one search; return False if the user cancelled.

    When ``customer_id`` is given (customer menu) only that customer's orders are searched.
    """
    modes = ["Order ID", "Customer name (keyword)", "Shipping status",
             "Payment status", "Order date range"]
    if customer_id is not None:
        modes.remove("Customer name (keyword)")
    mode = read_choice("Search by:", modes, allow_cancel=True)
    if mode is None:
        return False
    if mode == "Order ID":
        rows = get_orders(conn, order_id=read_int("Order ID: ", minimum=1), customer_id=customer_id)
    elif mode.startswith("Customer"):
        rows = get_orders(conn, customer_keyword=read_text("Name contains: "))
    elif mode == "Shipping status":
        rows = get_orders(conn, shipping_status=read_choice("Status:", SHIPPING_STATUSES),
                          customer_id=customer_id)
    elif mode == "Payment status":
        rows = get_orders(conn, payment_status=read_choice("Status:", PAYMENT_STATUSES),
                          customer_id=customer_id)
    else:
        start = read_date("From (YYYY-MM-DD): ")
        end = read_date("To   (YYYY-MM-DD): ")
        if start > end:
            print("The start date must not be after the end date.")
            return True
        rows = get_orders(conn, date_from=start, date_to=end, customer_id=customer_id)
    print(f"\n{len(rows)} order(s) found.")
    show_orders(rows)
    if rows:
        print(f"Combined value of matches: {format_money(sum(r['total'] for r in rows))}")
    return True

def search_orders_flow(conn, customer_id=None):
    """Search repeatedly until the user is done."""
    banner("Search Orders")
    while search_once(conn, customer_id):
        if not read_yes_no("\nSearch again?"):
            break

def update_order_flow(conn):
    """Update shipping status, payment status, parcel location or an item quantity."""
    banner("Update Order")
    order_id = read_int("Order ID to update: ", minimum=1)
    rows = get_orders(conn, order_id=order_id)
    if not rows:
        warn(f"No order with ID {order_id}. Nothing was changed.")
        return
    order = rows[0]
    show_orders(rows)

    field = read_choice("\nWhat do you want to update?",
                        ["Shipping status", "Payment status", "Parcel location (map)",
                         "Item quantity"], allow_cancel=True)
    if field is None:
        info("Update cancelled.")
        return

    if field == "Shipping status":
        options = allowed_next_statuses(order["shipping_status"])
        if not options:
            info(f"Orders that are {order['shipping_status']} are final; "
                 "their shipping status cannot change.")
            return
        status = read_choice(f"Currently {order['shipping_status']}. Move to:",
                             options, allow_cancel=True)
        if status is None:
            info("Update cancelled.")
            return
        update_order_status(conn, order_id, shipping_status=status)
        ok("Order updated.")
        print_route_map(get_orders(conn, order_id=order_id)[0])
        return
    elif field == "Payment status":
        status = read_choice("New payment status:", PAYMENT_STATUSES, allow_cancel=True)
        if status is None:
            info("Update cancelled.")
            return
        update_order_status(conn, order_id, payment_status=status)
    elif field == "Parcel location (map)":
        if order["shipping_status"] != "Shipped":
            info("The parcel location can be updated while the order is Shipped.")
            return
        stage = order_stage(order)
        if stage >= 3:
            info("The parcel is already out for delivery. "
                 "Set the shipping status to Delivered when it arrives.")
            return
        print_route_map(order)
        next_title = route_stops(order["city"])[stage + 1][0]
        if not read_yes_no(f"\nMove the parcel to '{next_title}'?"):
            info("Update cancelled.")
            return
        title = advance_parcel(conn, order_id)
        ok(f"Parcel is now at: {title}.")
        print_route_map(get_orders(conn, order_id=order_id)[0])
        return
    else:
        if order["shipping_status"] not in EDITABLE_STATUSES:
            info("Items can only be changed while an order is Pending or Processing.")
            return
        items = get_order_items(conn, order_id)
        print_table(["Item ID", "Product", "Qty"],
                    [[i["item_id"], i["product_name"], i["quantity"]] for i in items])
        item_id = read_int("Item ID: ", minimum=1)
        quantity = read_int("New quantity: ", minimum=1, maximum=1000)
        if not update_item_quantity(conn, order_id, item_id, quantity):
            warn(f"Item {item_id} is not part of order #{order_id}. Nothing was changed.")
            return
    ok("Order updated.")

def delete_order_flow(conn):
    """Delete an order after the user confirms."""
    banner("Delete Order")
    order_id = read_int("Order ID to delete: ", minimum=1)
    rows = get_orders(conn, order_id=order_id)
    if not rows:
        warn(f"No order with ID {order_id}. Nothing was deleted.")
        return
    show_orders(rows)
    if read_yes_no("Delete this order and all its items permanently?"):
        delete_order(conn, order_id)
        ok("Order deleted.")
    else:
        info("Deletion cancelled.")


def change_admin_password_flow(conn, admin):
    """Let the logged-in admin set a new password."""
    banner("Change Admin Password")
    if not verify_password(read_password("Current password: "), admin["password_hash"]):
        warn("Wrong current password. Nothing was changed.")
        return
    set_admin_password(conn, admin["admin_id"], read_new_password())
    ok("Admin password changed.")


MENU = [
    ("1", "View customers", view_customers_flow),
    ("2", "Place order", add_order_flow),
    ("3", "View all orders", view_orders_flow),
    ("4", "View order details (items)", order_details_flow),
    ("5", "Track an order (with delivery map)", track_order_flow),
    ("6", "Search orders", search_orders_flow),
    ("7", "Update order (status / parcel location)", update_order_flow),
    ("8", "Delete order", delete_order_flow),
    ("9", "Shipping & payment board", board_flow),
    ("10", "Confirm order", confirm_order_flow),
    ("11", "Change admin password", None),  # needs the logged-in admin; handled in admin_session()
    ("0", "Log out", None),
]
ACTIONS = {key: func for key, _, func in MENU if func}
LAST_OPTION = max(int(key) for key, _, _ in MENU)

# 7. LOGIN: administrator and customer accounts

def my_orders_flow(conn, customer_id):
    """List the logged-in customer's own orders."""
    banner("My Orders")
    show_orders(get_orders(conn, customer_id=customer_id))

def customer_update_item_flow(conn, customer_id):
    """Customer changes the quantity of an item on their own Pending order."""
    banner("Update My Order")
    order_id = read_int("Order ID: ", minimum=1)
    rows = get_orders(conn, order_id=order_id, customer_id=customer_id)
    if not rows:
        warn(f"No order with ID {order_id}.")
        return
    if rows[0]["shipping_status"] != "Pending":
        info("You can only change items while the order is Pending (not yet confirmed).")
        return
    print_table(["Item ID", "Product", "Qty"],
                [[i["item_id"], i["product_name"], i["quantity"]]
                 for i in get_order_items(conn, order_id)])
    item_id = read_int("Item ID: ", minimum=1)
    quantity = read_int("New quantity: ", minimum=1, maximum=1000)
    if update_item_quantity(conn, order_id, item_id, quantity):
        ok("Order updated.")
    else:
        warn(f"Item {item_id} is not part of order #{order_id}. Nothing was changed.")

def customer_cancel_order_flow(conn, customer_id):
    """Customer cancels their own Pending order."""
    banner("Cancel My Order")
    order_id = read_int("Order ID to cancel: ", minimum=1)
    rows = get_orders(conn, order_id=order_id, customer_id=customer_id)
    if not rows:
        warn(f"No order with ID {order_id}.")
        return
    if rows[0]["shipping_status"] != "Pending":
        info("Only Pending orders can be cancelled. Please contact the store.")
        return
    show_orders(rows)
    if read_yes_no("Cancel this order?"):
        update_order_status(conn, order_id, shipping_status="Cancelled")
        ok(f"Order #{order_id} cancelled.")
    else:
        info("Order not cancelled.")

def admin_session(conn, admin):
    """Admin menu loop; returns when the admin logs out."""
    while True:
        show_menu(conn)
        choice = input(f"\nSelect an option (0-{LAST_OPTION}): ").strip()
        if choice == "0":
            info("Logged out.")
            return
        if choice == "11":
            action = lambda c: change_admin_password_flow(c, admin)
        else:
            action = ACTIONS.get(choice)
        if action is None:
            warn(f"Invalid choice. Please enter a number from 0 to {LAST_OPTION}.")
            continue
        try:
            action(conn)
        except sqlite3.Error as error:
            warn(f"Database error: {error}. Your data was not changed.")

def customer_session(conn, customer):
    """Customer menu loop; a customer only sees and orders for their own account."""
    customer_id = customer["customer_id"]
    options = [
        ("1", "Place order", lambda: add_order_flow(conn, customer_id)),
        ("2", "View my orders", lambda: my_orders_flow(conn, customer_id)),
        ("3", "View order details (items)", lambda: order_details_flow(conn, customer_id)),
        ("4", "Track an order (with delivery map)", lambda: track_order_flow(conn, customer_id)),
        ("5", "Search my orders", lambda: search_orders_flow(conn, customer_id)),
        ("6", "Update my order (item quantity)", lambda: customer_update_item_flow(conn, customer_id)),
        ("7", "Cancel my order", lambda: customer_cancel_order_flow(conn, customer_id)),
    ]
    actions = {key: func for key, _, func in options}
    while True:
        print("\n" + "=" * 60)
        print(f"WELCOME, {customer['name']}")
        print("=" * 60)
        for key, label, _ in options:
            print(f"  {key}. {label}")
        print("  0. Log out")
        print("-" * 60)
        choice = input(f"Select an option (0-{len(options)}): ").strip()
        if choice == "0":
            info("Logged out.")
            return
        action = actions.get(choice)
        if action is None:
            warn(f"Invalid choice. Please enter a number from 0 to {len(options)}.")
            continue
        try:
            action()
        except sqlite3.Error as error:
            warn(f"Database error: {error}. Your data was not changed.")

MAX_LOGIN_ATTEMPTS = 3

def admin_login(conn):
    """Ask for admin credentials (3 tries); return the admin row or None."""
    banner("Admin Login")
    for _ in range(MAX_LOGIN_ATTEMPTS):
        username = read_text("Username (blank to cancel): ", required=False)
        if not username:
            return None
        admin = get_admin(conn, username)
        if admin and verify_password(read_password("Password: "), admin["password_hash"]):
            ok("Login successful.")
            return admin
        warn("Wrong username or password.")
    warn("Too many failed attempts.")
    return None

def customer_login(conn):
    """Ask for a customer's email and password (3 tries); return the customer row or None."""
    banner("Customer Login")
    for _ in range(MAX_LOGIN_ATTEMPTS):
        email = read_text("Email (blank to cancel): ", required=False).lower()
        if not email:
            return None
        customer = get_customer_by_email(conn, email)
        if customer and not customer["password_hash"]:
            # Older account without a password: verify the mobile number, then set one.
            print("  This account has no password yet. Please verify your mobile number.")
            phone = read_text("Mobile number: ")
            if is_valid_phone(phone) and customer["phone"] and normalize_phone(phone) == customer["phone"]:
                set_customer_password(conn, customer["customer_id"], read_new_password())
                ok("Password saved.")
                return get_customer_by_email(conn, email)
            warn("Email or mobile number is incorrect.")
            continue
        if customer and verify_password(read_password("Password: "), customer["password_hash"]):
            ok("Login successful.")
            return customer
        warn("Wrong email or password.")
    warn("Too many failed attempts.")
    return None

def main():
    """Show the login screen until the user exits."""
    conn = get_connection()
    create_tables(conn)
    try:
        while True:
            print("\n" + "=" * 60)
            print("ONLINE ORDER FULFILLMENT TRACKER - LOGIN")
            print("=" * 60)
            print("  1. Admin login")
            print("  2. Customer login")
            print("  3. Customer sign up")
            print("  0. Exit")
            choice = input("\nSelect an option (0-3): ").strip()
            if choice == "0":
                print("\nThank you for using the Online Order Fulfillment Tracker. Goodbye!\n")
                break
            try:
                if choice == "1":
                    admin = admin_login(conn)
                    if admin:
                        admin_session(conn, admin)
                elif choice == "2":
                    customer = customer_login(conn)
                    if customer:
                        customer_session(conn, customer)
                elif choice == "3":
                    customer = sign_up_flow(conn)
                    if customer:
                        info("You are now logged in.")
                        customer_session(conn, customer)
                else:
                    warn("Invalid choice. Please enter a number from 0 to 3.")
            except sqlite3.Error as error:
                warn(f"Database error: {error}. Your data was not changed.")
    except (KeyboardInterrupt, EOFError):
        print("\n\nGoodbye!\n")
    finally:
        conn.close()

if __name__ == "__main__":
    main()

