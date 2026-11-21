# Online Order Fulfillment Tracker

A web-based order management and fulfillment tracking system built with **Python, Flask, SQLite, HTML, CSS, and Matplotlib**. The system provides separate interfaces for administrators and customers to manage products, place orders, update fulfillment statuses, and monitor order progress.

## Features

### Customer
- Create an account and log in securely.
- Browse active products in the catalog.
- Place orders by selecting products and quantities.
- View personal order records and order details.
- Track shipping progress and view payment status.
- Review the tracking history of an order.

### Administrator
- View an administrative dashboard with order and customer summaries.
- Manage the product catalog: add, edit, activate, and deactivate products.
- View customer orders and their details.
- Update shipping and payment statuses.
- Review order and payment summaries and charts.

### Order and tracking
- Product names and prices are retrieved from the database when an order is submitted.
- Order item prices are saved with the order, preserving the price charged at the time of purchase.
- Shipping progress is recorded through status updates and tracking history.
- Customer accounts cannot access administrator-only product management pages.

> **Tracking note:** This project provides status-based order tracking. Package locations and route stops are illustrative fulfillment stages; the system does not use live GPS tracking.

## Technology Stack

- **Backend:** Python, Flask
- **Database:** SQLite
- **Frontend:** HTML, CSS, Jinja templates
- **Charts:** Matplotlib
- **Testing:** Python `unittest`

## Project Setup

### Requirements

- Python 3.10 or later
- Git

### 1. Clone the repository

```bash
git clone https://github.com/Czed54/-ONLINE-ORDER-FULFILLMENT-TRACKER.git
cd -ONLINE-ORDER-FULFILLMENT-TRACKER
```

### 2. Create and activate a virtual environment

**Windows (Git Bash):**

```bash
python -m venv .venv
source .venv/Scripts/activate
```

**Windows (Command Prompt):**

```bat
python -m venv .venv
.venv\Scripts\activate
```

### 3. Install dependencies

```bash
python -m pip install -r requirements.txt
```

### 4. Run the application

```bash
python app.py
```

Open the local address shown in the terminal, normally:

```text
http://127.0.0.1:5000
```

On first run, the application creates the SQLite database file (`DATABASE.db`) and required tables automatically.

## Demo Accounts

The database initializes a default administrator account when no administrator exists:

| Account | Username | Password |
|---|---|---|
| Administrator | `admin` | `admin123` |

Use the customer registration page to create a customer account for testing.


## Basic Demonstration Workflow

1. Sign in as the administrator and open **Products**.
2. Add a product with a name, description, and unit price.
3. Sign out and register or sign in as a customer.
4. Open **Place Order**, select an active product, enter a quantity, and submit the order.
5. Sign back in as the administrator and open the new order.
6. Update its shipping and payment statuses.
7. Sign in as the customer again and confirm that the updated statuses and tracking history are visible.
8. As an administrator, deactivate a product and confirm that it no longer appears in the customer order form.

## Running the Tests

From the project directory, with the virtual environment activated, run:

```bash
python -m unittest discover -s tests -v
```

To check Python syntax:

```bash
python -m py_compile app.py database.py
```

## Database and Local Data

The application uses SQLite and creates `DATABASE.db` locally. The database file is intentionally excluded from Git so that local customer, order, and product records are not uploaded with the source code. A fresh clone creates a new database on its first run.

Keep a separate backup of the database if you need to preserve local demonstration records.

## Repository

[GitHub Repository](https://github.com/Czed54/-ONLINE-ORDER-FULFILLMENT-TRACKER)
