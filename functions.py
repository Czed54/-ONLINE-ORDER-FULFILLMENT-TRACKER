"""functions.py - reusable functions: validation, passwords, formatting, input helpers,
business rules and the delivery-route helpers.

Online Order Fulfillment Tracker - DSA 214 Final Laboratory Activity (Scenario 14).
"""

import getpass
import hashlib
import html
import os
import re
import secrets
import urllib.parse
from datetime import date, datetime


EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

PHONE_PATTERN = re.compile(r"^(?:\+?63|0)?9\d{9}$")

ALLOWED_TRANSITIONS = {
    "Pending": ["Processing", "Cancelled"],
    "Processing": ["Shipped", "Cancelled"],
    "Shipped": ["Delivered"],
    "Delivered": [],
    "Cancelled": [],
}

EDITABLE_STATUSES = ("Pending", "Processing")  # items may only change before shipping

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
