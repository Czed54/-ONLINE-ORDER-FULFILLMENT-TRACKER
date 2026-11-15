"""
Laboratory Activity 6
Online Order Fulfillment Tracker
Python Functions and Documentation
"""

import math


def validate_order_items(items):
    """Validate order items and return the validated list."""
    if not isinstance(items, list) or not items:
        raise ValueError("An order must contain at least one item.")

    validated_items = []

    for item in items:
        if not isinstance(item, (tuple, list)) or len(item) != 3:
            raise ValueError("Each item must contain a name, quantity, and price.")

        name, quantity, price = item

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Product name cannot be empty.")

        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Quantity must be a positive integer.")

        if isinstance(price, bool) or not isinstance(price, (int, float)):
            raise ValueError("Price must be a valid number.")

        if not math.isfinite(price) or price < 0:
            raise ValueError("Price cannot be negative or non-finite.")

        validated_items.append((name.strip(), quantity, float(price)))

    return validated_items


def calculate_order_total(items, discount=0.0):
    """Calculate and return the total order cost after discount."""
    validated_items = validate_order_items(items)

    if isinstance(discount, bool) or not isinstance(discount, (int, float)):
        raise ValueError("Discount must be a valid number.")

    if not math.isfinite(discount) or not 0 <= discount <= 100:
        raise ValueError("Discount must be between 0 and 100 percent.")

    subtotal = sum(quantity * price for _, quantity, price in validated_items)
    total = subtotal - (subtotal * discount / 100)

    return round(total, 2)


def generate_order_summary(
    order_id,
    customer_name,
    items,
    shipping_status="Pending"
):
    """Generate and return a dictionary containing order information."""
    if isinstance(order_id, bool) or not isinstance(order_id, int) or order_id <= 0:
        raise ValueError("Order ID must be a positive integer.")

    if not isinstance(customer_name, str) or not customer_name.strip():
        raise ValueError("Customer name cannot be empty.")

    if not isinstance(shipping_status, str) or not shipping_status.strip():
        raise ValueError("Shipping status cannot be empty.")

    validated_items = validate_order_items(items)
    total = calculate_order_total(validated_items)

    return {
        "order_id": order_id,
        "customer": customer_name.strip(),
        "items": validated_items,
        "total": total,
        "shipping_status": shipping_status.strip()
    }


def format_order_report(summary):
    """Format an order summary into a readable text report."""
    if not isinstance(summary, dict):
        raise ValueError("Order summary must be a dictionary.")

    required_fields = {
        "order_id", "customer", "items", "total", "shipping_status"
    }

    if not required_fields.issubset(summary):
        raise ValueError("Order summary is missing required information.")

    lines = [
        "========== ORDER REPORT ==========",
        f"Order ID: {summary['order_id']}",
        f"Customer: {summary['customer']}",
        f"Shipping Status: {summary['shipping_status']}",
        "----------------------------------",
        "Purchased Items:"
    ]

    for name, quantity, price in summary["items"]:
        lines.append(
            f"{name} x {quantity} - PHP {price:.2f}"
        )

    lines.extend([
        "----------------------------------",
        f"Total: PHP {summary['total']:.2f}",
        "=================================="
    ])

    return "\n".join(lines)


def main():
    """Run the order report demonstration and three test cases."""
    print("ONLINE ORDER FULFILLMENT TRACKER")
    print("LABORATORY ACTIVITY 6 DEMONSTRATION")

    # Test 1: Normal order calculation.
    normal_items = [
        ("Notebook", 2, 50.00),
        ("Ballpen", 3, 15.00)
    ]

    print("\nTEST CASE 1 - Normal Order")
    summary = generate_order_summary(
        101, "Juan Dela Cruz", normal_items,
        shipping_status="Processing"
    )

    print(format_order_report(summary))
    assert summary["total"] == 145.00
    print("PASS - Expected total: PHP 145.00")

    # Test 2: Keyword argument and discount calculation.
    print("\nTEST CASE 2 - Discounted Order")
    discounted_total = calculate_order_total(
        normal_items, discount=10
    )

    print(f"Actual total: PHP {discounted_total:.2f}")
    assert discounted_total == 130.50
    print("PASS - Expected total: PHP 130.50")

    # Test 3: Invalid quantity must raise an error.
    print("\nTEST CASE 3 - Invalid Quantity")
    try:
        calculate_order_total([("Notebook", 0, 50.00)])
    except ValueError as error:
        print("PASS - Invalid quantity rejected:", error)
    else:
        raise AssertionError("Invalid quantity was accepted")

    print("\\nAll 3 test cases passed.")


if __name__ == "__main__":
    main()
