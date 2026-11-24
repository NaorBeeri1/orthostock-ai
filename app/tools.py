from datetime import datetime, timedelta
from typing import Optional
import uuid
from app.database import get_connection

BRANCH_ALIASES = {
    "br-rlz": "BR-RLZ",
    "ראשון": "BR-RLZ",
    "ראשון לציון": "BR-RLZ",
    "rishon": "BR-RLZ",
    "br-rmg": "BR-RMG",
    "רמת גן": "BR-RMG",
    "ramat gan": "BR-RMG",
    "br-ptk": "BR-PTK",
    "פתח תקווה": "BR-PTK",
    "petah tikva": "BR-PTK",
}


def _normalize_branch(val: Optional[str]) -> Optional[str]:
    if not val:
        return None
    cleaned = val.strip().lower()
    if cleaned in BRANCH_ALIASES:
        return BRANCH_ALIASES[cleaned]
    for key, code in BRANCH_ALIASES.items():
        if key in cleaned:
            return code
    return val.strip()


def search_inventory(
    query: Optional[str] = None,
    category: Optional[str] = None,
    warehouse: Optional[str] = None,
) -> dict:
    """Search orthopedic products, footwear, and braces and check current stock levels across branches.

    Args:
        query: Product name in Hebrew or English, brand, keyword, or SKU (e.g., 'הוקה', 'HOKA', 'לומבולוק', 'בלנדסטון', 'SHOE-HOKA-KAHA2').
        category: Optional category filter ('נעליים', 'חגורות גב', 'חגורות בטן', 'אביזרי מפרקים', 'שיקום ונוחות').
        warehouse: Optional branch ID ('BR-RLZ', 'BR-RMG', 'BR-PTK') or Hebrew/English city name ('ראשון לציון', 'רמת גן', 'פתח תקווה').
    """
    conn = get_connection()
    cur = conn.cursor()

    sql = """
        SELECT
            p.sku,
            p.name,
            p.category,
            p.unit_cost AS unit_cost_ils,
            p.reorder_point,
            p.supplier,
            w.id AS branch_id,
            w.city AS branch_city,
            s.quantity
        FROM products p
        JOIN stock_levels s ON p.sku = s.sku
        JOIN warehouses w ON s.warehouse_id = w.id
        WHERE 1=1
    """
    params = []

    if query:
        sql += " AND (LOWER(p.name) LIKE ? OR LOWER(p.sku) LIKE ?)"
        term = f"%{query.lower()}%"
        params.extend([term, term])

    if category:
        sql += " AND LOWER(p.category) LIKE ?"
        params.append(f"%{category.lower()}%")

    norm_wh = _normalize_branch(warehouse)
    if norm_wh:
        sql += " AND (UPPER(w.id) = ? OR LOWER(w.city) LIKE ?)"
        params.extend([norm_wh.upper(), f"%{norm_wh.lower()}%"])

    sql += " ORDER BY p.sku, w.id"
    rows = [dict(r) for r in cur.execute(sql, params).fetchall()]
    conn.close()

    return {
        "count": len(rows),
        "results": rows,
    }


def get_low_stock_alerts(warehouse: Optional[str] = None) -> dict:
    """Find orthopedic products or footwear whose total stock across all branches is at or below their reorder point,
    or items completely out of stock (0 units) in a specific branch.

    Args:
        warehouse: Optional branch ID ('BR-RLZ', 'BR-RMG', 'BR-PTK') or city name ('ראשון לציון', 'רמת גן', 'פתח תקווה').
    """
    conn = get_connection()
    cur = conn.cursor()

    global_sql = """
        SELECT
            p.sku,
            p.name,
            p.category,
            p.reorder_point,
            p.supplier,
            p.lead_time_days,
            COALESCE(SUM(s.quantity), 0) AS total_stock,
            (p.reorder_point - COALESCE(SUM(s.quantity), 0)) AS deficit
        FROM products p
        LEFT JOIN stock_levels s ON p.sku = s.sku
        GROUP BY p.sku
        HAVING total_stock <= p.reorder_point
        ORDER BY deficit DESC
    """
    low_global = [dict(r) for r in cur.execute(global_sql).fetchall()]

    local_sql = """
        SELECT
            p.sku,
            p.name,
            w.id AS branch_id,
            w.city AS branch_city,
            s.quantity
        FROM stock_levels s
        JOIN products p ON s.sku = p.sku
        JOIN warehouses w ON s.warehouse_id = w.id
        WHERE s.quantity = 0
    """
    params = []
    norm_wh = _normalize_branch(warehouse)
    if norm_wh:
        local_sql += " AND (UPPER(w.id) = ? OR LOWER(w.city) LIKE ?)"
        params.extend([norm_wh.upper(), f"%{norm_wh.lower()}%"])

    zero_local = [dict(r) for r in cur.execute(local_sql, params).fetchall()]
    conn.close()

    return {
        "global_low_stock_items": low_global,
        "zero_stock_by_branch": zero_local,
    }


def check_incoming_orders(sku: Optional[str] = None, status: Optional[str] = None) -> dict:
    """Check purchase orders (incoming supplier shipments or pending manager approvals).

    Args:
        sku: Optional product SKU to filter orders (e.g., 'SHOE-HOKA-KAHA2').
        status: Optional order status ('IN_TRANSIT', 'PENDING_APPROVAL', 'DELIVERED').
    """
    conn = get_connection()
    cur = conn.cursor()

    sql = """
        SELECT
            po.po_number,
            po.sku,
            p.name AS product_name,
            po.warehouse_id AS branch_id,
            w.city AS destination_city,
            po.quantity,
            po.status,
            po.expected_date
        FROM purchase_orders po
        JOIN products p ON po.sku = p.sku
        JOIN warehouses w ON po.warehouse_id = w.id
        WHERE 1=1
    """
    params = []

    if sku:
        sql += " AND LOWER(po.sku) LIKE ?"
        params.append(f"%{sku.lower()}%")

    if status:
        sql += " AND UPPER(po.status) = ?"
        params.append(status.upper())

    sql += " ORDER BY po.expected_date ASC"
    orders = [dict(r) for r in cur.execute(sql, params).fetchall()]
    conn.close()

    return {
        "order_count": len(orders),
        "orders": orders,
    }


def calculate_restock_cost(sku: str, quantity: int) -> dict:
    """Calculate total restock cost in ILS (₪), bulk discount eligibility, and expected delivery date for a product.

    Args:
        sku: Exact product SKU (e.g., 'SHOE-HOKA-KAHA2').
        quantity: Number of units or pairs to order (must be > 0).
    """
    if quantity <= 0:
        return {"error": "הכמות חייבת להיות גדולה מ-0."}

    conn = get_connection()
    cur = conn.cursor()
    row = cur.execute(
        "SELECT sku, name, unit_cost, supplier, lead_time_days FROM products WHERE LOWER(sku) = ?",
        (sku.lower(),),
    ).fetchone()
    conn.close()

    if not row:
        return {"error": f"מק״ט '{sku}' לא נמצא במערכת."}

    product = dict(row)
    subtotal = product["unit_cost"] * quantity
    discount_rate = 0.10 if quantity >= 25 else (0.05 if quantity >= 10 else 0.0)
    discount_amount = round(subtotal * discount_rate, 2)
    total_cost = round(subtotal - discount_amount, 2)
    eta = str((datetime.now().date() + timedelta(days=product["lead_time_days"])))

    return {
        "sku": product["sku"],
        "product_name": product["name"],
        "supplier": product["supplier"],
        "quantity": quantity,
        "unit_cost_ils": product["unit_cost"],
        "discount_rate_pct": int(discount_rate * 100),
        "total_cost_ils": total_cost,
        "lead_time_days": product["lead_time_days"],
        "estimated_arrival": eta,
    }


def draft_purchase_order(sku: str, quantity: int, warehouse_id: str) -> dict:
    """Create a DRAFT purchase order with status 'PENDING_APPROVAL' for branch manager review.
    Never finalizes payment or supplier dispatch without manager sign-off.

    Args:
        sku: Product SKU (e.g., 'SHOE-HOKA-KAHA2', 'SUPP-RHIZ-LOC').
        quantity: Number of units or pairs to order (1 to 500).
        warehouse_id: Target branch ID ('BR-RLZ', 'BR-RMG', 'BR-PTK') or Hebrew city name ('ראשון לציון', 'רמת גן', 'פתח תקווה').
    """
    if quantity <= 0 or quantity > 500:
        return {"error": "הכמות חייבת להיות בין 1 ל-500 יחידות."}

    valid_branches = {"BR-RLZ", "BR-RMG", "BR-PTK"}
    branch = (_normalize_branch(warehouse_id) or "").upper()
    if branch not in valid_branches:
        return {"error": f"קוד סניף לא תקין '{warehouse_id}'. יש לבחור מתוך: ראשון לציון (BR-RLZ), רמת גן (BR-RMG), או פתח תקווה (BR-PTK)."}

    conn = get_connection()
    cur = conn.cursor()
    product = cur.execute(
        "SELECT sku, name, unit_cost, lead_time_days FROM products WHERE LOWER(sku) = ?",
        (sku.lower(),),
    ).fetchone()

    if not product:
        conn.close()
        return {"error": f"מק״ט '{sku}' לא קיים במערכת."}

    po_number = f"PO-2026-{uuid.uuid4().hex[:4].upper()}"
    expected_date = str(datetime.now().date() + timedelta(days=product["lead_time_days"]))

    cur.execute(
        """
        INSERT INTO purchase_orders (po_number, sku, warehouse_id, quantity, status, expected_date)
        VALUES (?, ?, ?, ?, 'PENDING_APPROVAL', ?)
        """,
        (po_number, product["sku"], branch, quantity, expected_date),
    )
    conn.commit()
    conn.close()

    return {
        "status": "CREATED_PENDING_APPROVAL",
        "po_number": po_number,
        "sku": product["sku"],
        "product_name": product["name"],
        "branch_id": branch,
        "quantity": quantity,
        "estimated_cost_ils": round(product["unit_cost"] * quantity, 2),
        "expected_date": expected_date,
        "note": "טיוטת הזמנת הרכש נשמרה וממתינה לאישור מנהל תפעול/סניף לפני שליחה לספק.",
    }


ALL_TOOLS = [
    search_inventory,
    get_low_stock_alerts,
    check_incoming_orders,
    calculate_restock_cost,
    draft_purchase_order,
]