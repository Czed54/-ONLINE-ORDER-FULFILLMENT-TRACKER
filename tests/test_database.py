
import sqlite3
import tempfile
import unittest
from pathlib import Path

from database import (
    Customer,
    add_customer,
    add_order,
    advance_parcel,
    confirm_order,
    create_tables,
    customer_exists,
    delete_order,
    get_admin,
    get_customer_by_id,
    update_customer,
    delete_customer,
    get_connection,
    get_customer_by_email,
    get_customers,
    get_order_items,
    get_orders,
    get_quick_stats,
    get_status_history,
    update_item_quantity,
    update_order_status,
)


class DatabaseTests(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.conn = get_connection(self.db_path)
        create_tables(self.conn)

        customer = Customer(
            name="Test Customer",
            email="test@example.com",
            city="Manila",
            phone="09123456789"
        )
        self.customer_id = add_customer(self.conn, customer)

    def tearDown(self):
        self.conn.close()
        self.temp_dir.cleanup()

    def test_tables_and_default_admin(self):
        tables = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()

        table_names = {row["name"] for row in tables}

        self.assertIn("customers", table_names)
        self.assertIn("orders", table_names)
        self.assertIn("order_items", table_names)
        self.assertIn("admins", table_names)
        self.assertIsNotNone(get_admin(self.conn, "admin"))

    def test_add_and_find_customer(self):
        customer = get_customer_by_email(
            self.conn, "test@example.com"
        )

        self.assertIsNotNone(customer)
        self.assertEqual(customer["name"], "Test Customer")
        self.assertTrue(customer_exists(self.conn, self.customer_id))
        self.assertEqual(len(get_customers(self.conn)), 1)


    def test_get_customer_by_id(self):
        customer = get_customer_by_id(
            self.conn, self.customer_id
        )

        self.assertIsNotNone(customer)
        self.assertEqual(customer["name"], "Test Customer")
        self.assertEqual(customer["email"], "test@example.com")

    def test_update_customer(self):
        updated = update_customer(
            self.conn,
            self.customer_id,
            "Updated Customer",
            "updated@example.com",
            "Cebu",
            "09987654321"
        )

        customer = get_customer_by_id(
            self.conn, self.customer_id
        )

        self.assertTrue(updated)
        self.assertEqual(customer["name"], "Updated Customer")
        self.assertEqual(customer["email"], "updated@example.com")
        self.assertEqual(customer["city"], "Cebu")
        self.assertEqual(customer["phone"], "09987654321")

    def test_delete_customer_without_orders(self):
        deleted = delete_customer(
            self.conn, self.customer_id
        )

        self.assertTrue(deleted)
        self.assertIsNone(
            get_customer_by_id(self.conn, self.customer_id)
        )

    def test_delete_customer_with_orders(self):
        add_order(
            self.conn,
            self.customer_id,
            "2026-11-11",
            [("Notebook", 1, 50.00)]
        )

        with self.assertRaises(sqlite3.IntegrityError):
            delete_customer(self.conn, self.customer_id)

        self.assertIsNotNone(
            get_customer_by_id(self.conn, self.customer_id)
        )

    def test_duplicate_customer_email(self):
        duplicate = Customer(
            name="Another Customer",
            email="test@example.com",
            city="Quezon City"
        )

        with self.assertRaises(sqlite3.IntegrityError):
            add_customer(self.conn, duplicate)

    def test_add_and_retrieve_order(self):
        order_id = add_order(
            self.conn,
            self.customer_id,
            "2026-11-11",
            [("Notebook", 2, 50.00), ("Pen", 5, 10.00)]
        )

        orders = get_orders(self.conn, order_id=order_id)
        items = get_order_items(self.conn, order_id)

        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["total"], 150.00)
        self.assertEqual(orders[0]["item_count"], 7)
        self.assertEqual(len(items), 2)

    def test_order_history(self):
        order_id = add_order(
            self.conn,
            self.customer_id,
            "2026-11-11",
            [("Notebook", 1, 50.00)]
        )

        history = get_status_history(self.conn, order_id)

        self.assertGreaterEqual(len(history), 1)
        self.assertEqual(history[0]["event"], "Order placed")

    def test_confirm_order(self):
        order_id = add_order(
            self.conn,
            self.customer_id,
            "2026-11-11",
            [("Notebook", 1, 50.00)]
        )

        self.assertTrue(confirm_order(self.conn, order_id))
        self.assertEqual(
            get_orders(self.conn, order_id=order_id)[0]["shipping_status"],
            "Processing"
        )

    def test_update_shipping_and_payment(self):
        order_id = add_order(
            self.conn,
            self.customer_id,
            "2026-11-11",
            [("Notebook", 1, 50.00)]
        )

        result = update_order_status(
            self.conn,
            order_id,
            shipping_status="Shipped",
            payment_status="Paid"
        )

        order = get_orders(self.conn, order_id=order_id)[0]

        self.assertTrue(result)
        self.assertEqual(order["shipping_status"], "Shipped")
        self.assertEqual(order["payment_status"], "Paid")

    def test_update_item_quantity(self):
        order_id = add_order(
            self.conn,
            self.customer_id,
            "2026-11-11",
            [("Notebook", 2, 50.00)]
        )

        item_id = get_order_items(self.conn, order_id)[0]["item_id"]

        self.assertTrue(
            update_item_quantity(self.conn, order_id, item_id, 5)
        )
        self.assertEqual(
            get_order_items(self.conn, order_id)[0]["quantity"], 5
        )

    def test_advance_parcel(self):
        order_id = add_order(
            self.conn,
            self.customer_id,
            "2026-11-11",
            [("Notebook", 1, 50.00)],
            shipping_status="Shipped"
        )

        result = advance_parcel(self.conn, order_id)

        self.assertIsNotNone(result)
        self.assertGreater(
            get_orders(self.conn, order_id=order_id)[0]["route_stage"], 1
        )

    def test_quick_stats(self):
        add_order(
            self.conn,
            self.customer_id,
            "2026-11-11",
            [("Notebook", 1, 50.00)]
        )

        stats = get_quick_stats(self.conn)

        self.assertEqual(stats["customers"], 1)
        self.assertEqual(stats["orders"], 1)
        self.assertEqual(stats["to_ship"], 1)
        self.assertEqual(stats["unpaid"], 1)

    def test_delete_order(self):
        order_id = add_order(
            self.conn,
            self.customer_id,
            "2026-11-11",
            [("Notebook", 1, 50.00)]
        )

        self.assertTrue(delete_order(self.conn, order_id))
        self.assertEqual(get_orders(self.conn, order_id=order_id), [])
        self.assertEqual(get_order_items(self.conn, order_id), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
