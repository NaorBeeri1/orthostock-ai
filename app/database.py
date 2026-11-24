import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

DB_PATH = Path(__file__).parent.parent / "inventory.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_and_seed_db(force_reset: bool = False) -> None:
    if DB_PATH.exists() and not force_reset:
        return

    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = get_connection()
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE warehouses (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        city TEXT NOT NULL
    );

    CREATE TABLE products (
        sku TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit_cost REAL NOT NULL,
        reorder_point INTEGER NOT NULL,
        supplier TEXT NOT NULL,
        lead_time_days INTEGER NOT NULL
    );

    CREATE TABLE stock_levels (
        sku TEXT NOT NULL,
        warehouse_id TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        PRIMARY KEY (sku, warehouse_id),
        FOREIGN KEY (sku) REFERENCES products(sku),
        FOREIGN KEY (warehouse_id) REFERENCES warehouses(id)
    );

    CREATE TABLE purchase_orders (
        po_number TEXT PRIMARY KEY,
        sku TEXT NOT NULL,
        warehouse_id TEXT NOT NULL,
        quantity INTEGER NOT NULL,
        status TEXT NOT NULL, -- 'IN_TRANSIT', 'PENDING_APPROVAL', 'DELIVERED'
        expected_date TEXT NOT NULL,
        FOREIGN KEY (sku) REFERENCES products(sku)
    );
    """)

    branches = [
        ("BR-RLZ", "סניף ראשון לציון (רוטשילד 37)", "ראשון לציון"),
        ("BR-RMG", "סניף רמת גן (ארלוזורוב 5)", "רמת גן"),
        ("BR-PTK", "סניף פתח תקווה (בר כוכבא 33)", "פתח תקווה"),
    ]
    cur.executemany("INSERT INTO warehouses VALUES (?, ?, ?)", branches)

    products = [
        ("SHOE-HOKA-KAHA2", "נעלי הוקה קאהה 2 גברים שחור (HOKA Kaha 2 GTX)", "נעליים", 849.00, 12, "הוקה ישראל הפצה", 10),
        ("SHOE-BLND-1977", "מגפי עקב בלנדסטון 1977 נשים שחור (Blundstone)", "נעליים", 449.00, 15, "בלנדסטון יבוא בע״מ", 7),
        ("SHOE-BLND-1673", "מגפי עור בלנדסטון 1673 חום עתיק (Blundstone)", "נעליים", 419.00, 10, "בלנדסטון יבוא בע״מ", 7),
        ("SHOE-ASIC-GEL9", "נעלי ספורט אסיקס ילדים (Asics Gel-Contend 9)", "נעליים", 299.00, 18, "אסיקס ספורט סיטונאות", 5),
        ("SHOE-CROC-NAVY", "כפכפי קרוקס נייבי (Crocs Crocband Navy)", "נעליים", 209.00, 20, "קומפורט סטפ ישראל", 4),
        ("BRCE-LUMB-TRN", "חגורת גב לומבוטריין עם רפידת עיסוי (LumboTrain)", "חגורות גב", 1000.00, 8, "באוארפיינד מדיקל ישראל", 14),
        ("BRCE-LUMB-FRT", "חגורת גב מחוזקת לומבולוק פורטה (LumboLoc Forte)", "חגורות גב", 499.00, 10, "באוארפיינד מדיקל ישראל", 14),
        ("BRCE-OPPO-2160", "חגורת בטן חובקת דגם 2160 (OPPO)", "חגורות בטן", 249.00, 15, "אופו ציוד רפואי", 6),
        ("SUPP-ACHL-TRN", "תומך גיד אכילס אכילוטריין (AchilloTrain)", "אביזרי מפרקים", 399.00, 12, "באוארפיינד מדיקל ישראל", 12),
        ("SUPP-RHIZ-LOC", "מייצב אגודל ריזולוק (RhizoLoc)", "אביזרי מפרקים", 299.00, 10, "באוארפיינד מדיקל ישראל", 12),
        ("SUPP-OMO-TRN", "תומך כתף אומוטריין (OmoTrain)", "אביזרי מפרקים", 1199.00, 6, "באוארפיינד מדיקל ישראל", 14),
        ("REHB-TENS-XPD12", "מכשיר טנס לשיכוך כאבים (HiDow TENS XPD 12)", "שיקום ונוחות", 799.00, 9, "מדטק שיקום בע״מ", 5),
        ("REHB-AHOR-CUSH", "כרית ישיבה אורטופדית (AHORA Seat Cushion)", "שיקום ונוחות", 299.00, 14, "אהורה וולנס", 4),
    ]
    cur.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", products)

    stock = [
        ("SHOE-HOKA-KAHA2", "BR-RLZ", 3), ("SHOE-HOKA-KAHA2", "BR-RMG", 0), ("SHOE-HOKA-KAHA2", "BR-PTK", 4),
        ("SHOE-BLND-1977", "BR-RLZ", 8), ("SHOE-BLND-1977", "BR-RMG", 6), ("SHOE-BLND-1977", "BR-PTK", 5),
        ("SHOE-BLND-1673", "BR-RLZ", 1), ("SHOE-BLND-1673", "BR-RMG", 0), ("SHOE-BLND-1673", "BR-PTK", 2),
        ("SHOE-ASIC-GEL9", "BR-RLZ", 10), ("SHOE-ASIC-GEL9", "BR-RMG", 7), ("SHOE-ASIC-GEL9", "BR-PTK", 6),
        ("SHOE-CROC-NAVY", "BR-RLZ", 12), ("SHOE-CROC-NAVY", "BR-RMG", 9), ("SHOE-CROC-NAVY", "BR-PTK", 8),
        ("BRCE-LUMB-TRN", "BR-RLZ", 4), ("BRCE-LUMB-TRN", "BR-RMG", 3), ("BRCE-LUMB-TRN", "BR-PTK", 3),
        ("BRCE-LUMB-FRT", "BR-RLZ", 2), ("BRCE-LUMB-FRT", "BR-RMG", 0), ("BRCE-LUMB-FRT", "BR-PTK", 1),
        ("BRCE-OPPO-2160", "BR-RLZ", 9), ("BRCE-OPPO-2160", "BR-RMG", 6), ("BRCE-OPPO-2160", "BR-PTK", 5),
        ("SUPP-ACHL-TRN", "BR-RLZ", 5), ("SUPP-ACHL-TRN", "BR-RMG", 4), ("SUPP-ACHL-TRN", "BR-PTK", 5),
        ("SUPP-RHIZ-LOC", "BR-RLZ", 4), ("SUPP-RHIZ-LOC", "BR-RMG", 2), ("SUPP-RHIZ-LOC", "BR-PTK", 2),
        ("SUPP-OMO-TRN", "BR-RLZ", 3), ("SUPP-OMO-TRN", "BR-RMG", 2), ("SUPP-OMO-TRN", "BR-PTK", 2),
        ("REHB-TENS-XPD12", "BR-RLZ", 5), ("REHB-TENS-XPD12", "BR-RMG", 3), ("REHB-TENS-XPD12", "BR-PTK", 4),
        ("REHB-AHOR-CUSH", "BR-RLZ", 2), ("REHB-AHOR-CUSH", "BR-RMG", 0), ("REHB-AHOR-CUSH", "BR-PTK", 3),
    ]
    cur.executemany("INSERT INTO stock_levels VALUES (?, ?, ?)", stock)

    today = datetime.now().date()
    orders = [
        ("PO-2026-401", "SHOE-HOKA-KAHA2", "BR-RMG", 15, "IN_TRANSIT", str(today + timedelta(days=3))),
        ("PO-2026-405", "BRCE-LUMB-FRT", "BR-RLZ", 12, "IN_TRANSIT", str(today + timedelta(days=5))),
        ("PO-2026-409", "SHOE-BLND-1673", "BR-RMG", 10, "PENDING_APPROVAL", str(today + timedelta(days=7))),
        ("PO-2026-412", "REHB-AHOR-CUSH", "BR-PTK", 20, "IN_TRANSIT", str(today + timedelta(days=2))),
    ]
    cur.executemany("INSERT INTO purchase_orders VALUES (?, ?, ?, ?, ?, ?)", orders)

    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_and_seed_db(force_reset=True)
    print(f"Hebrew orthopedic inventory database seeded successfully at {DB_PATH}")