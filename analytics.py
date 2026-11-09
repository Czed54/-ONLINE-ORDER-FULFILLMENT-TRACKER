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