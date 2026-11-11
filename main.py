"""main.py - login, menus and program flow.

DSA 214 - Final Laboratory Activity - Scenario 14 (Online Order Fulfillment Tracker).
"""

import sqlite3
import webbrowser
from datetime import date

from analytics import print_board, write_map_page
from database import Customer, PAYMENT_STATUSES, SHIPPING_STATUSES, add_customer, add_order, advance_parcel, confirm_order, create_tables, customer_exists, delete_order, get_admin, get_connection, get_customer_by_email, get_customers, get_order_items, get_orders, get_quick_stats, get_status_history, set_admin_password, set_customer_password, update_item_quantity, update_order_status
from functions import print_route_map, EDITABLE_STATUSES, allowed_next_statuses, banner, calculate_order_total, format_money, hash_password, info, is_valid_phone, normalize_phone, ok, order_stage, paginate, print_table, read_choice, read_date, read_email, read_float, read_int, read_name, read_new_password, read_password, read_phone, read_text, read_yes_no, route_stops, verify_password, warn

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
        ok(f"Account created. Your customer ID is {customer_id}. You can now log in.")
    except sqlite3.IntegrityError:
        warn("A customer with that email already exists. Nothing was saved.")

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

def search_once(conn):
    """Run one search; return False if the user cancelled."""
    mode = read_choice("Search by:", [
        "Order ID", "Customer name (keyword)", "Shipping status",
        "Payment status", "Order date range"], allow_cancel=True)
    if mode is None:
        return False
    if mode == "Order ID":
        rows = get_orders(conn, order_id=read_int("Order ID: ", minimum=1))
    elif mode.startswith("Customer"):
        rows = get_orders(conn, customer_keyword=read_text("Name contains: "))
    elif mode == "Shipping status":
        rows = get_orders(conn, shipping_status=read_choice("Status:", SHIPPING_STATUSES))
    elif mode == "Payment status":
        rows = get_orders(conn, payment_status=read_choice("Status:", PAYMENT_STATUSES))
    else:
        start = read_date("From (YYYY-MM-DD): ")
        end = read_date("To   (YYYY-MM-DD): ")
        if start > end:
            print("The start date must not be after the end date.")
            return True
        rows = get_orders(conn, date_from=start, date_to=end)
    print(f"\n{len(rows)} order(s) found.")
    show_orders(rows)
    if rows:
        print(f"Combined value of matches: {format_money(sum(r['total'] for r in rows))}")
    return True

def search_orders_flow(conn):
    """Search repeatedly until the user is done."""
    banner("Search Orders")
    while search_once(conn):
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
        ("1", "View my orders", lambda: my_orders_flow(conn, customer_id)),
        ("2", "View order details (items)", lambda: order_details_flow(conn, customer_id)),
        ("3", "Track an order (with delivery map)", lambda: track_order_flow(conn, customer_id)),
        ("4", "Place order", lambda: add_order_flow(conn, customer_id)),
    ]
    while True:
        print("\n" + "=" * 60)
        print(f"WELCOME, {customer['name']}")
        print("=" * 60)
        for key, label, _ in options:
            print(f"  {key}. {label}")
        print("  0. Log out")
        print("-" * 60)
        choice = input("Select an option (0-4): ").strip()
        if choice == "0":
            info("Logged out.")
            return
        action = {key: func for key, _, func in options}.get(choice)
        if action is None:
            warn("Invalid choice. Please enter a number from 0 to 4.")
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
                    sign_up_flow(conn)
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
