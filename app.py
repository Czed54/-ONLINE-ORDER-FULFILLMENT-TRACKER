"""Flask web interface for the Online Order Fulfillment Tracker."""

import os
import sqlite3
from datetime import date
from functools import wraps
from pathlib import Path

from flask import (
    Flask, abort, flash, g, redirect, render_template,
    request, send_file, session, url_for
)

from database import (
    Customer, PAYMENT_STATUSES, SHIPPING_STATUSES,
    add_customer, add_order, confirm_order, create_tables,
    add_product, get_products, get_product_by_id,
    update_product, set_product_active,
    get_admin, get_connection, get_customer_by_email,
    get_customer_by_id, get_order_items, get_orders,
    get_quick_stats, get_status_history, update_order_status,
    advance_parcel
)
from analytics import (
    chart_orders_by_status, chart_revenue_by_payment,
    average_order_value, top_customers
)
from functions import (
    allowed_next_statuses, hash_password, is_valid_email,
    is_valid_name, is_valid_phone, normalize_phone,
    verify_password, format_money,
    order_stage, route_stops, where_is_order, map_url
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "change-this-development-key")

BASE_DIR = Path(__file__).resolve().parent
CHARTS_DIR = BASE_DIR / "charts"


# ---------------------------------------------------------
# DATABASE CONNECTION
# ---------------------------------------------------------

def get_db():
    if "db" not in g:
        g.db = get_connection()
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


with app.app_context():
    conn = get_db()
    create_tables(conn)


# ---------------------------------------------------------
# AUTHENTICATION
# ---------------------------------------------------------

def login_required(role=None):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("login"))

            if role and session.get("role") != role:
                abort(403)

            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        conn = get_db()
        role = request.form.get("role", "customer")
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        phone = request.form.get("phone", "")
        new_password = request.form.get("new_password", "")

        if role == "admin":
            admin = get_admin(conn, username)

            if admin and verify_password(password, admin["password_hash"]):
                session.clear()
                session["user_id"] = admin["admin_id"]
                session["role"] = "admin"
                session["display_name"] = admin["username"]
                flash("Welcome back, administrator.", "success")
                return redirect(url_for("dashboard"))

            flash("Invalid administrator username or password.", "danger")

        elif role == "customer":
            customer = get_customer_by_email(conn, username.lower())

            if not customer:
                flash("No customer account was found with that email.", "danger")

            elif not customer["password_hash"]:
                if (
                    is_valid_phone(phone)
                    and customer["phone"]
                    and normalize_phone(phone) == customer["phone"]
                    and len(new_password) >= 8
                ):
                    from database import set_customer_password
                    set_customer_password(
                        conn, customer["customer_id"], new_password
                    )
                    customer = get_customer_by_email(conn, username.lower())
                    session.clear()
                    session["user_id"] = customer["customer_id"]
                    session["role"] = "customer"
                    session["display_name"] = customer["name"]
                    flash("Password created. You are now logged in.", "success")
                    return redirect(url_for("dashboard"))
                else:
                    flash(
                        "This account needs a password. Verify your mobile "
                        "number and enter a new password of at least 8 characters.",
                        "warning"
                    )

            elif verify_password(password, customer["password_hash"]):
                session.clear()
                session["user_id"] = customer["customer_id"]
                session["role"] = "customer"
                session["display_name"] = customer["name"]
                flash("Login successful.", "success")
                return redirect(url_for("dashboard"))

            else:
                flash("Incorrect customer password.", "danger")

        else:
            flash("Invalid account type.", "danger")

    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        city = request.form.get("city", "").strip()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")

        if not is_valid_name(name):
            flash("Enter a valid name.", "danger")
        elif not is_valid_email(email):
            flash("Enter a valid email address.", "danger")
        elif not is_valid_phone(phone):
            flash("Enter a valid Philippine mobile number.", "danger")
        elif not city or len(city) > 60:
            flash("Enter a city (maximum 60 characters).", "danger")
        elif len(password) < 8:
            flash("Password must contain at least 8 characters.", "danger")
        elif password != confirm:
            flash("Passwords do not match.", "danger")
        else:
            try:
                customer = Customer(
                    name=name,
                    email=email,
                    city=city,
                    phone=normalize_phone(phone),
                    password_hash=hash_password(password)
                )
                customer_id = add_customer(get_db(), customer)

                flash(
                    f"Registration successful! Your customer ID is {customer_id}.",
                    "success"
                )
                return redirect(url_for("login"))

            except sqlite3.IntegrityError:
                flash("That email address is already registered.", "danger")

    return render_template("register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))


# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------

@app.route("/dashboard")
@login_required()
def dashboard():
    conn = get_db()

    if session["role"] == "admin":
        stats = get_quick_stats(conn)
        orders = get_orders(conn)[:8]

        status_chart = chart_orders_by_status(conn)
        payment_chart = chart_revenue_by_payment(conn)

        return render_template(
            "dashboard.html",
            role="admin",
            stats=stats,
            orders=orders,
            average_value=average_order_value(conn),
            top_customers=top_customers(conn),
            status_chart=status_chart.name if status_chart else None,
            payment_chart=payment_chart.name if payment_chart else None,
            money=format_money
        )

    customer_id = session["user_id"]
    orders = get_orders(conn, customer_id=customer_id)
    customer = get_customer_by_id(conn, customer_id)

    return render_template(
        "dashboard.html",
        role="customer",
        customer=customer,
        orders=orders[:8],
        stats=None,
        money=format_money
    )



# ---------------------------------------------------------
# PRODUCT CATALOG (ADMIN)
# ---------------------------------------------------------

@app.route("/products", methods=["GET", "POST"])
@login_required("admin")
def products():
    conn = get_db()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        price = request.form.get("unit_price", "").strip()
        product_id = request.form.get("product_id", "").strip()

        try:
            if product_id:
                updated = update_product(
                    conn, int(product_id), name, description, price
                )
                if not updated:
                    flash("Product not found.", "warning")
                else:
                    flash("Product updated successfully.", "success")
            else:
                add_product(conn, name, description, price)
                flash("Product added to the catalog.", "success")
        except ValueError as exc:
            flash(str(exc), "danger")
        except sqlite3.IntegrityError:
            flash("A product with that name already exists.", "danger")

        return redirect(url_for("products"))

    editing = None
    edit_id = request.args.get("edit", "").strip()
    if edit_id:
        try:
            editing = get_product_by_id(conn, int(edit_id))
            if editing is None:
                flash("Product not found.", "warning")
        except ValueError:
            flash("Invalid product selection.", "danger")

    return render_template(
        "products.html",
        products=get_products(conn, include_inactive=True),
        editing=editing,
        money=format_money
    )


@app.route("/products/<int:product_id>/toggle", methods=["POST"])
@login_required("admin")
def toggle_product(product_id):
    conn = get_db()
    product = get_product_by_id(conn, product_id)

    if product is None:
        abort(404)

    new_state = not bool(product["is_active"])
    set_product_active(conn, product_id, new_state)
    flash(
        "Product activated." if new_state else "Product deactivated.",
        "success"
    )
    return redirect(url_for("products"))


# ---------------------------------------------------------
# ORDERS
# ---------------------------------------------------------

@app.route("/orders")
@login_required()
def orders():
    conn = get_db()

    if session["role"] == "admin":
        rows = get_orders(
            conn,
            shipping_status=request.args.get("shipping_status") or None,
            payment_status=request.args.get("payment_status") or None
        )
    else:
        rows = get_orders(conn, customer_id=session["user_id"])

    return render_template(
        "orders.html",
        orders=rows,
        shipping_statuses=SHIPPING_STATUSES,
        payment_statuses=PAYMENT_STATUSES,
        money=format_money
    )


@app.route("/orders/new", methods=["GET", "POST"])
@login_required("customer")
def new_order():
    conn = get_db()
    available_products = get_products(conn)

    if request.method == "POST":
        product_ids = request.form.getlist("product_id[]")
        quantities = request.form.getlist("quantity[]")
        items = []

        try:
            if not available_products:
                raise ValueError("No products are currently available.")

            if (
                not product_ids
                or len(product_ids) != len(quantities)
                or len(product_ids) > 20
            ):
                raise ValueError("Please check your order items.")

            seen_ids = set()

            for raw_id, raw_quantity in zip(product_ids, quantities):
                product_id = int(raw_id)
                quantity = int(raw_quantity)

                if product_id in seen_ids:
                    raise ValueError("Please select each product only once.")
                seen_ids.add(product_id)

                if quantity < 1 or quantity > 1000:
                    raise ValueError("Quantity must be between 1 and 1000.")

                product = get_product_by_id(conn, product_id)
                if product is None or not product["is_active"]:
                    raise ValueError(
                        "One of your selected products is no longer available."
                    )

                # Use the catalog name and price, never submitted client prices.
                items.append((
                    product["name"],
                    quantity,
                    product["unit_price"]
                ))

            order_date = (
                request.form.get("order_date")
                or date.today().isoformat()
            )
            parsed_date = date.fromisoformat(order_date)

            if parsed_date > date.today():
                raise ValueError("Order date cannot be in the future.")

            order_id = add_order(
                conn,
                session["user_id"],
                order_date,
                items,
                payment_status="Unpaid"
            )

            flash(
                f"Order #{order_id} submitted. Waiting for admin confirmation.",
                "success"
            )
            return redirect(url_for("order_detail", order_id=order_id))

        except (ValueError, TypeError, OverflowError) as exc:
            flash(str(exc) or "Please check your order details.", "danger")

    return render_template(
        "new_order.html",
        today=date.today().isoformat(),
        products=available_products,
        money=format_money
    )


@app.route("/orders/<int:order_id>")
@login_required()
def order_detail(order_id):
    conn = get_db()
    rows = get_orders(conn, order_id=order_id)

    if not rows:
        abort(404)

    order = rows[0]

    if (
        session["role"] == "customer"
        and order["customer_id"] != session["user_id"]
    ):
        abort(403)

    items = get_order_items(conn, order_id)
    history = get_status_history(conn, order_id)

    return render_template(
        "order_detail.html",
        order=order,
        items=items,
        history=history,
        tracking=build_tracking(order),
        role=session["role"],
        next_statuses=allowed_next_statuses(order["shipping_status"]),
        payment_statuses=PAYMENT_STATUSES,
        money=format_money
    )


# --- tracking page ---

STEP_LABELS = ["Order placed", "Processing", "Shipped", "Out for delivery", "Delivered"]


def build_tracking(order):
    """Everything the tracking view needs, derived from the order row."""
    status = order["shipping_status"]
    stage = order_stage(order)  # 0-4, or None when cancelled
    where = where_is_order(order)

    if status == "Cancelled":
        return {"cancelled": True, "where": where, "steps": [], "stops": [],
                "maps_url": None, "badge": "Cancelled"}

    if status == "Delivered":
        current = 5  # every step done
    elif stage == 3:
        current = 3
    elif stage in (1, 2):
        current = 2
    elif status == "Processing":
        current = 1
    else:
        current = 0

    notes = {0: order["order_date"],
             2: order["shipped_date"],
             4: order["delivered_date"]}
    steps = []
    for i, label in enumerate(STEP_LABELS):
        state = "done" if i < current else "current" if i == current else "todo"
        steps.append({"label": label, "state": state, "note": notes.get(i) if state != "todo" else None})

    stops = []
    for i, (title, _place) in enumerate(route_stops(order["city"])):
        state = "done" if i < stage or stage == 4 else "current" if i == stage else "todo"
        stops.append({"title": title, "state": state})

    badge = "Out for delivery" if stage == 3 and status == "Shipped" else status
    maps_url = map_url(where["map_place"]) if where["map_place"] else None
    return {"cancelled": False, "where": where, "steps": steps, "stops": stops,
            "maps_url": maps_url, "badge": badge, "can_advance": status == "Shipped" and stage < 3}


@app.route("/orders/<int:order_id>/advance", methods=["POST"])
@login_required("admin")
def advance_parcel_route(order_id):
    stop = advance_parcel(get_db(), order_id)
    if stop:
        flash(f"Parcel moved to: {stop}.", "success")
    else:
        flash("This parcel can't move to a new stop. It must be Shipped and not yet out for delivery.", "warning")
    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/orders/<int:order_id>/confirm", methods=["POST"])
@login_required("admin")
def confirm_order_route(order_id):
    if confirm_order(get_db(), order_id):
        flash(f"Order #{order_id} confirmed and moved to Processing.", "success")
    else:
        flash("This order could not be confirmed. It may no longer be Pending.", "warning")

    return redirect(url_for("order_detail", order_id=order_id))


@app.route("/orders/<int:order_id>/update", methods=["POST"])
@login_required("admin")
def update_order_route(order_id):
    conn = get_db()
    rows = get_orders(conn, order_id=order_id)

    if not rows:
        abort(404)

    current = rows[0]
    new_shipping = request.form.get("shipping_status")
    new_payment = request.form.get("payment_status")

    if new_shipping:
        if new_shipping not in allowed_next_statuses(current["shipping_status"]):
            flash("That shipping status transition is not allowed.", "danger")
            return redirect(url_for("order_detail", order_id=order_id))

    if new_payment and new_payment not in PAYMENT_STATUSES:
        flash("Invalid payment status.", "danger")
        return redirect(url_for("order_detail", order_id=order_id))

    update_order_status(
        conn,
        order_id,
        shipping_status=new_shipping or None,
        payment_status=new_payment or None
    )

    flash("Order status updated.", "success")
    return redirect(url_for("order_detail", order_id=order_id))


# ---------------------------------------------------------
# CHART FILES
# ---------------------------------------------------------

@app.route("/charts/<path:filename>")
@login_required("admin")
def chart_file(filename):
    path = (CHARTS_DIR / filename).resolve()

    if path.parent != CHARTS_DIR.resolve() or not path.is_file():
        abort(404)

    return send_file(path, mimetype="image/png")


if __name__ == "__main__":
    app.run(debug=True)
