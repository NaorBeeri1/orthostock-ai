import pytest
from app.database import init_and_seed_db
from app.tools import (
    search_inventory,
    get_low_stock_alerts,
    check_incoming_orders,
    calculate_restock_cost,
    draft_purchase_order,
)
from app.agent import run_inventory_agent


@pytest.fixture(autouse=True)
def reset_db():
    init_and_seed_db(force_reset=True)
    yield


def test_search_inventory_by_hebrew_and_english():
    res_eng = search_inventory(query="HOKA")
    assert res_eng["count"] == 3  # Across BR-RLZ, BR-RMG, BR-PTK

    res_heb = search_inventory(query="הוקה", warehouse="רמת גן")
    assert res_heb["count"] == 1
    assert res_heb["results"][0]["branch_id"] == "BR-RMG"
    assert res_heb["results"][0]["quantity"] == 0


def test_low_stock_and_incoming_orders():
    alerts = get_low_stock_alerts()
    low_skus = {item["sku"] for item in alerts["global_low_stock_items"]}
    assert "SHOE-HOKA-KAHA2" in low_skus
    assert "SUPP-RHIZ-LOC" in low_skus

    orders = check_incoming_orders(sku="SHOE-HOKA-KAHA2", status="IN_TRANSIT")
    assert orders["order_count"] == 1
    assert orders["orders"][0]["branch_id"] == "BR-RMG"


def test_restock_cost_bulk_discount():
    quote = calculate_restock_cost("SHOE-HOKA-KAHA2", quantity=15)
    assert quote["discount_rate_pct"] == 5
    assert quote["total_cost_ils"] == round(849.00 * 15 * 0.95, 2)


def test_draft_po_guardrails():
    # Invalid branch rejected
    bad_branch = draft_purchase_order("SUPP-RHIZ-LOC", 10, "WH-INVALID")
    assert "error" in bad_branch

    # Valid draft created in PENDING_APPROVAL state
    valid_po = draft_purchase_order("SUPP-RHIZ-LOC", 10, "רמת גן")
    assert valid_po["status"] == "CREATED_PENDING_APPROVAL"
    assert valid_po["branch_id"] == "BR-RMG"
    assert valid_po["po_number"].startswith("PO-2026-")


def test_end_to_end_hebrew_agent_tool_calling():
    result = run_inventory_agent(
        "כמה זוגות נעלי הוקה קאהה 2 יש בסניף רמת גן, והאם יש הזמנה בדרך?"
    )
    invoked = [t["tool"] for t in result["tool_trace"]]
    assert "search_inventory" in invoked
    assert "check_incoming_orders" in invoked
    assert "15" in result["reply"]