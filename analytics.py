"""Analytics for the Online Order Fulfillment Tracker.

Calculates summary measures from the SQLite database and generates charts.
All figures come from the stored records; cancelled orders are excluded
from revenue figures because they were never fulfilled.
"""

from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # save to files; no window needed (CLI only)
import matplotlib.pyplot as plt

CHARTS_DIR = Path(__file__).resolve().parent / "charts"


# ---------------------------------------------------------------- measures
def orders_by_shipping_status(conn):
    """Return [(shipping_status, order_count), ...] sorted by count."""
    rows = conn.execute(
        """SELECT shipping_status, COUNT(*)
           FROM orders
           GROUP BY shipping_status
           ORDER BY COUNT(*) DESC"""
    ).fetchall()
    return [(r[0], r[1]) for r in rows]


def revenue_by_payment_status(conn):
    """Return [(payment_status, revenue), ...] for non-cancelled orders."""
    rows = conn.execute(
        """SELECT o.payment_status, SUM(i.quantity * i.unit_price)
           FROM orders o
           JOIN order_items i ON i.order_id = o.order_id
           WHERE o.shipping_status != 'Cancelled'
           GROUP BY o.payment_status
           ORDER BY SUM(i.quantity * i.unit_price) DESC"""
    ).fetchall()
    return [(r[0], r[1] or 0.0) for r in rows]


def average_order_value(conn):
    """Return the average order total (non-cancelled orders), or 0.0 if none."""
    row = conn.execute(
        """SELECT AVG(order_total) FROM (
               SELECT SUM(i.quantity * i.unit_price) AS order_total
               FROM orders o
               JOIN order_items i ON i.order_id = o.order_id
               WHERE o.shipping_status != 'Cancelled'
               GROUP BY o.order_id
           )"""
    ).fetchone()
    return row[0] or 0.0


def top_customers(conn, limit=5):
    """Return [(name, order_count, total_spent), ...] ranked by total spent."""
    rows = conn.execute(
        """SELECT c.name, COUNT(DISTINCT o.order_id),
                  SUM(i.quantity * i.unit_price) AS total_spent
           FROM customers c
           JOIN orders o ON o.customer_id = c.customer_id
           JOIN order_items i ON i.order_id = o.order_id
           WHERE o.shipping_status != 'Cancelled'
           GROUP BY c.customer_id
           ORDER BY total_spent DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [(r[0], r[1], r[2] or 0.0) for r in rows]


# ------------------------------------------------------------------ charts
def _bar_chart(labels, values, title, xlabel, ylabel, filename, money=False):
    """Draw a bar chart and save it in the charts folder. Return the path."""
    CHARTS_DIR.mkdir(exist_ok=True)
    fig, ax = plt.subplots(figsize=(7, 4.5))
    bars = ax.bar(labels, values, color="#4C78A8")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    for bar, value in zip(bars, values):
        text = f"{value:,.2f}" if money else str(value)
        ax.annotate(text, (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                    ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    path = CHARTS_DIR / filename
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return path


def chart_orders_by_status(conn):
    """Chart 1: number of orders per shipping status. Return path or None."""
    data = orders_by_shipping_status(conn)
    if not data:
        return None
    labels, values = zip(*data)
    return _bar_chart(labels, values, "Orders by Shipping Status",
                      "Shipping status", "Number of orders",
                      "orders_by_shipping_status.png")


def chart_revenue_by_payment(conn):
    """Chart 2: revenue per payment status. Return path or None."""
    data = revenue_by_payment_status(conn)
    if not data:
        return None
    labels, values = zip(*data)
    return _bar_chart(labels, values, "Order Value by Payment Status",
                      "Payment status", "Total value",
                      "revenue_by_payment_status.png", money=True)


# ------------------------------------------------------------- CLI report
def show_analytics(conn):
    """Print all measures and generate both charts (call from the menu)."""
    print("\n=== ORDER ANALYTICS ===")

    print("\n1. Orders by shipping status")
    data = orders_by_shipping_status(conn)
    if not data:
        print("   No orders recorded yet.")
        return
    for status, count in data:
        print(f"   {status:<12} {count}")

    print("\n2. Order value by payment status (excluding cancelled)")
    for status, total in revenue_by_payment_status(conn):
        print(f"   {status:<12} {total:>12,.2f}")

    print(f"\n3. Average order value: {average_order_value(conn):,.2f}")

    print("\n4. Top customers by total spent")
    for rank, (name, orders, spent) in enumerate(top_customers(conn), start=1):
        print(f"   {rank}. {name:<20} {orders} order(s)  {spent:>12,.2f}")

    print("\nGenerating charts...")
    for path in (chart_orders_by_status(conn), chart_revenue_by_payment(conn)):
        if path:
            print(f"   Saved: {path}")

# ----------------------------------------------------------- CLI integration
def print_board(conn):
    """Display order counts and values grouped by shipping/payment status."""
    from database import shipping_summary, payment_summary

    print("\n=== SHIPPING BOARD ===")
    print(f"{'Shipping status':<16} {'Orders':>8} {'Order value':>16}")
    print("-" * 42)
    for status, count, amount in shipping_summary(conn):
        print(f"{status:<16} {count:>8} {amount:>16,.2f}")

    print("\n=== PAYMENT BOARD ===")
    print(f"{'Payment status':<16} {'Orders':>8} {'Order value':>16}")
    print("-" * 42)
    for status, count, amount in payment_summary(conn):
        print(f"{status:<16} {count:>8} {amount:>16,.2f}")


def write_map_page(conn, order_id):
    """Create a local HTML tracking page for an order and return its Path."""
    import html
    from urllib.parse import quote

    from database import get_order_items, get_orders
    from functions import MAP_PAGE_TEMPLATE, map_url, route_map_lines, where_is_order

    rows = get_orders(conn, order_id=order_id)
    if not rows:
        return None

    order = rows[0]
    items = get_order_items(conn, order_id)
    where = where_is_order(order)

    title = f"Order #{order_id} - Delivery Tracking"
    subtitle = f"Customer: {order['customer']} | Destination: {order['city']}"
    item_rows = "".join(
        "<tr><td>{}</td><td>{}</td><td>{}</td><td>{:,.2f}</td></tr>".format(
            html.escape(str(item["product_name"])),
            item["quantity"],
            html.escape(f"PHP {item['unit_price']:,.2f}"),
            item["quantity"] * item["unit_price"],
        )
        for item in items
    )
    route_rows = "".join(
        "<tr><td>{}</td></tr>".format(html.escape(line.strip()))
        for line in route_map_lines(order)
    )
    map_place = where["map_place"] or order["city"]
    embed_url = "https://www.google.com/maps?q=" + quote(map_place) + "&output=embed"
    link_url = map_url(map_place)
    total = sum(item["quantity"] * item["unit_price"] for item in items)

    replacements = {
        "@@TITLE@@": html.escape(title),
        "@@SUB@@": html.escape(subtitle),
        "@@HEADLINE@@": html.escape(where["headline"]),
        "@@EMBED@@": html.escape(embed_url, quote=True),
        "@@LINK@@": html.escape(link_url, quote=True),
        "@@ROUTE@@": route_rows,
        "@@ITEMS@@": item_rows,
        "@@TOTAL@@": html.escape(f"PHP {total:,.2f}"),
    }
    page = MAP_PAGE_TEMPLATE
    for marker, value in replacements.items():
        page = page.replace(marker, value)

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = CHARTS_DIR / f"order_{order_id}_tracking.html"
    output_path.write_text(page, encoding="utf-8")
    return output_path

