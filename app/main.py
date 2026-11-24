from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from app.database import init_and_seed_db, get_connection
from app.agent import run_inventory_agent

BASE_DIR = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_and_seed_db(force_reset=False)
    yield


app = FastAPI(
    title="OrthoStock AI — Retail & Medical Inventory Copilot",
    description="Tool-calling LLM backend over a multi-branch orthopedic SQLite inventory database.",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str = Field(..., pattern="^(user|model)$")
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatMessage] = Field(default_factory=list)


@app.get("/")
def serve_dashboard():
    return FileResponse(BASE_DIR / "static" / "index.html")


@app.get("/health")
def health_check():
    return {"status": "ok", "service": "orthostock-agent"}


@app.get("/inventory")
def get_full_inventory():
    """Returns a live snapshot of orthopedic products and stock across branches for the dashboard UI."""
    conn = get_connection()
    rows = conn.execute("""
        SELECT
            p.sku,
            p.name,
            p.category,
            p.unit_cost,
            p.reorder_point,
            SUM(CASE WHEN s.warehouse_id = 'BR-RLZ' THEN s.quantity ELSE 0 END) AS rlz_stock,
            SUM(CASE WHEN s.warehouse_id = 'BR-RMG' THEN s.quantity ELSE 0 END) AS rmg_stock,
            SUM(CASE WHEN s.warehouse_id = 'BR-PTK' THEN s.quantity ELSE 0 END) AS ptk_stock,
            SUM(s.quantity) AS total_stock
        FROM products p
        LEFT JOIN stock_levels s ON p.sku = s.sku
        GROUP BY p.sku
        ORDER BY p.category, p.sku
    """).fetchall()
    orders = conn.execute("SELECT * FROM purchase_orders ORDER BY expected_date ASC").fetchall()
    conn.close()
    return {
        "products": [dict(r) for r in rows],
        "purchase_orders": [dict(r) for r in orders],
    }


@app.post("/chat")
def chat_endpoint(payload: ChatRequest):
    try:
        history_dicts = [m.model_dump() for m in payload.history]
        return run_inventory_agent(payload.message, history=history_dicts)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))