"""Adds the customer tracking page to the Order Fulfillment Tracker.

Run from the project folder (the one containing app.py):
    python apply_tracking.py

It backs up each file it touches (*.pre-tracking.bak), refuses to run twice,
and syntax-checks app.py at the end. Everything shown on the page comes from
the database (orders, order_items, order_status_history) and the existing
route/stage helpers in functions.py. Nothing is simulated.
"""
import py_compile
import shutil
import sys
from pathlib import Path

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
APP = ROOT / "app.py"
TEMPLATE = ROOT / "templates" / "order_detail.html"
CSS = ROOT / "static" / "style.css"
MARK = "# --- tracking page ---"

for p in (APP, TEMPLATE, CSS):
    if not p.exists():
        sys.exit(f"Missing {p}. Run this from the project folder.")

app_src = APP.read_bytes().decode("utf-8")
if MARK in app_src:
    sys.exit("Tracking page is already applied. Nothing to do.")

NL = "\r\n" if "\r\n" in app_src else "\n"
fix = lambda s: s.replace("\r\n", "\n").replace("\n", NL)

def swap(src, old, new):
    old, new = fix(old), fix(new)
    if src.count(old) != 1:
        sys.exit(f"app.py doesn't look like the expected version (couldn't find: {old.strip()[:50]!r}).")
    return src.replace(old, new)

app_src = swap(app_src,
    "get_quick_stats, get_status_history, update_order_status\n)",
    "get_quick_stats, get_status_history, update_order_status,\n    advance_parcel\n)")
app_src = swap(app_src,
    "verify_password, format_money\n)",
    "verify_password, format_money,\n    order_stage, route_stops, where_is_order, map_url\n)")
app_src = swap(app_src,
    "        history=history,\n",
    "        history=history,\n        tracking=build_tracking(order),\n")

HELPERS = '''# --- tracking page ---

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


'''
app_src = swap(app_src,
    '@app.route("/orders/<int:order_id>/confirm", methods=["POST"])',
    HELPERS + '@app.route("/orders/<int:order_id>/confirm", methods=["POST"])')

TEMPLATE_SRC = r'''{% extends "base.html" %}

{% block title %}Order #{{ order.order_id }} | Order Fulfillment Tracker{% endblock %}

{% block content %}
<div class="page-header">
    <h2>Order #{{ order.order_id }}</h2>
    <p>{{ tracking.where.headline }}</p>
</div>

<section class="panel" aria-labelledby="trk-progress">
    <div class="section-heading">
        <h3 id="trk-progress">Progress</h3>
        <span class="status-badge trk-badge{% if tracking.cancelled %} trk-cancelled{% endif %}">
            <span aria-hidden="true">{{ "✕" if tracking.cancelled else "●" }}</span> {{ tracking.badge }}
        </span>
    </div>

    {% if tracking.cancelled %}
    <p class="trk-note">This order was cancelled and won't be delivered.</p>
    {% else %}
    <ol class="trk-steps" aria-label="Order progress">
        {% for step in tracking.steps %}
        <li class="trk-step {{ step.state }}"{% if step.state == "current" %} aria-current="step"{% endif %}>
            <span class="trk-dot" aria-hidden="true">{% if step.state == "done" %}✓{% else %}{{ loop.index }}{% endif %}</span>
            <span class="trk-text">
                <strong>{{ step.label }}</strong>
                <small>{% if step.state == "current" %}Current{% elif step.state == "done" %}Done{% else %}Not yet{% endif %}{% if step.note %} · {{ step.note }}{% endif %}</small>
            </span>
        </li>
        {% endfor %}
    </ol>
    {% endif %}
</section>

<div class="trk-grid">
    {% if not tracking.cancelled %}
    <section class="panel" aria-labelledby="trk-where">
        <h3 id="trk-where">Package location</h3>
        <p class="trk-place">{{ tracking.where.place }}</p>
        <ol class="trk-route">
            {% for stop in tracking.stops %}
            <li class="{{ stop.state }}"{% if stop.state == "current" %} aria-current="step"{% endif %}>
                <span aria-hidden="true">{% if stop.state == "done" %}✓{% elif stop.state == "current" %}●{% else %}○{% endif %}</span>
                {{ stop.title }}
            </li>
            {% endfor %}
        </ol>
        <div class="trk-actions">
            {% if tracking.maps_url %}
            <a class="btn btn-secondary" href="{{ tracking.maps_url }}" target="_blank" rel="noopener">View on map</a>
            {% endif %}
            {% if role == "admin" and tracking.can_advance %}
            <form method="POST" action="{{ url_for('advance_parcel_route', order_id=order.order_id) }}">
                <button type="submit" class="btn">Move to next stop</button>
            </form>
            {% endif %}
        </div>
    </section>
    {% endif %}

    <section class="panel" aria-labelledby="trk-history">
        <h3 id="trk-history">Tracking history</h3>
        {% if history %}
        <div class="timeline">
            {% for event in history|reverse %}
            <div class="timeline-item">
                <strong>{{ event.event }}</strong>
                <p>{{ event.changed_at }}</p>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <p>No tracking updates yet.</p>
        {% endif %}
    </section>
</div>

<section class="panel" aria-labelledby="trk-summary">
    <div class="section-heading">
        <h3 id="trk-summary">Order summary</h3>
        <button type="button" class="btn btn-secondary trk-copy" id="trkCopy" data-copy="#{{ order.order_id }}">Copy order number</button>
    </div>

    <div class="details-grid">
        <p><strong>Order date:</strong> {{ order.order_date }}</p>
        <p><strong>Payment:</strong> {{ order.payment_status }}</p>
        <p><strong>Shipped:</strong> {{ order.shipped_date or "Not shipped yet" }}</p>
        <p><strong>Delivered:</strong> {{ order.delivered_date or "Not delivered yet" }}</p>
        <p><strong>Delivering to:</strong> {{ order.city }}</p>
        {% if role == "admin" %}
        <p><strong>Customer:</strong> {{ order.customer }}</p>
        <p><strong>Phone:</strong> {{ order.phone }}</p>
        {% endif %}
    </div>

    {% if items %}
    <div class="table-container">
        <table>
            <thead>
                <tr><th>Product</th><th>Quantity</th><th>Unit price</th><th>Subtotal</th></tr>
            </thead>
            <tbody>
                {% for item in items %}
                <tr>
                    <td>{{ item.product_name }}</td>
                    <td>{{ item.quantity }}</td>
                    <td>{{ money(item.unit_price) }}</td>
                    <td>{{ money(item.line_total) }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% endif %}

    <div class="order-total">
        <strong>Order total:</strong>
        <span>{{ money(order.total) }}</span>
    </div>
</section>

{% if role == "admin" %}
<div class="panel">
    <h3>Order Management</h3>

    {% if order.shipping_status == "Pending" %}
    <form method="POST" action="{{ url_for('confirm_order_route', order_id=order.order_id) }}">
        <button type="submit" class="btn">Confirm Order</button>
    </form>
    {% endif %}

    <form method="POST" action="{{ url_for('update_order_route', order_id=order.order_id) }}" class="management-form">
        <div>
            <label for="shipping_status">Shipping Status</label>
            <select name="shipping_status" id="shipping_status">
                <option value="">Keep Current Status</option>
                {% for status in next_statuses %}
                <option value="{{ status }}">{{ status }}</option>
                {% endfor %}
            </select>
        </div>

        <div>
            <label for="payment_status">Payment Status</label>
            <select name="payment_status" id="payment_status">
                <option value="">Keep Current Status</option>
                {% for status in payment_statuses %}
                <option value="{{ status }}" {% if status == order.payment_status %}selected{% endif %}>{{ status }}</option>
                {% endfor %}
            </select>
        </div>

        <button type="submit" class="btn">Update Order</button>
    </form>
</div>
{% endif %}

<a href="{{ url_for('orders') }}" class="btn btn-secondary">Back to Orders</a>

<script>
    (function () {
        var btn = document.getElementById("trkCopy");
        if (!btn) return;
        btn.addEventListener("click", function () {
            var text = btn.getAttribute("data-copy");
            var done = function () {
                btn.textContent = "Copied";
                setTimeout(function () { btn.textContent = "Copy order number"; }, 1800);
            };
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text).then(done, function () {});
            }
        });
    })();
</script>
{% endblock %}
'''

CSS_SRC = '''

/* =========================================
   Tracking page
   ========================================= */

.trk-badge { display: inline-flex; align-items: center; gap: 6px; }
.trk-badge.trk-cancelled { background: transparent; border: 1px solid var(--danger); color: var(--danger); }
.trk-note { color: var(--muted); margin: 8px 0 0; }

.trk-steps { list-style: none; margin: 18px 0 0; padding: 0; display: grid; gap: 0; }
.trk-step { position: relative; display: flex; gap: 14px; padding-bottom: 20px; }
.trk-step:last-child { padding-bottom: 0; }
.trk-step::before { content: ""; position: absolute; left: 15px; top: 32px; bottom: 0; width: 2px; background: var(--border); }
.trk-step:last-child::before { display: none; }
.trk-step.done::before { background: var(--success); }
.trk-dot {
    flex: none; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center;
    border: 2px solid var(--border); background: var(--surface); color: var(--muted);
    font-weight: 700; font-variant-numeric: tabular-nums; position: relative; z-index: 1;
}
.trk-step.done .trk-dot { background: var(--success); border-color: var(--success); color: #fff; }
.trk-step.current .trk-dot { background: var(--primary); border-color: var(--primary); color: var(--surface); box-shadow: 0 0 0 5px var(--surface-secondary); }
.trk-text strong { display: block; }
.trk-text small { color: var(--muted); font-variant-numeric: tabular-nums; }
.trk-step.todo .trk-text strong { color: var(--muted); font-weight: 500; }

.trk-grid { display: grid; gap: 20px; margin-bottom: 20px; }
.trk-grid > .panel { margin-bottom: 0; }
.trk-place { font-size: 20px; font-weight: 700; margin: 4px 0 12px; }
.trk-route { list-style: none; margin: 0 0 16px; padding: 0; }
.trk-route li { padding: 5px 0; color: var(--muted); }
.trk-route li span { display: inline-block; width: 1.4em; }
.trk-route li.done { color: var(--text); }
.trk-route li.current { color: var(--text); font-weight: 700; }
.trk-actions { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
.trk-actions form { margin: 0; }
.trk-copy { min-height: 40px; }

@media (min-width: 760px) {
    .trk-steps { grid-template-columns: repeat(5, 1fr); }
    .trk-step { flex-direction: column; align-items: center; text-align: center; padding: 0 6px; gap: 10px; }
    .trk-step::before { left: calc(50% + 22px); right: calc(-50% + 22px); top: 15px; bottom: auto; width: auto; height: 2px; }
    .trk-grid { grid-template-columns: 1fr 1fr; }
}
'''

for p in (APP, TEMPLATE, CSS):
    shutil.copy2(p, p.with_name(p.name + ".pre-tracking.bak"))

APP.write_bytes(app_src.encode("utf-8"))
TEMPLATE.write_bytes(TEMPLATE_SRC.encode("utf-8"))
css = CSS.read_bytes().decode("utf-8")
css_nl = "\r\n" if "\r\n" in css else "\n"
CSS.write_bytes((css.rstrip() + CSS_SRC.replace("\n", css_nl)).encode("utf-8"))

py_compile.compile(str(APP), doraise=True)
print("Done. app.py, templates/order_detail.html and static/style.css updated (backups: *.pre-tracking.bak).")
print("Restart Flask, log in, and open any order.")
