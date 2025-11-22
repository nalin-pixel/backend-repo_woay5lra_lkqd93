import os
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import MenuItem, Order, OrderItem, Rider, Slot

app = FastAPI(title="CloudChef API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"name": "CloudChef", "status": "ok"}

# Utility

def collection_name(model_cls):
    return model_cls.__name__.lower()

# Menu Endpoints

@app.get("/api/menu", response_model=List[MenuItem])
def list_menu():
    docs = get_documents(collection_name(MenuItem), {"is_active": True})
    # Convert ObjectId to string and map to schema
    items: List[MenuItem] = []
    for d in docs:
        d.pop("_id", None)
        items.append(MenuItem(**d))
    return items

@app.post("/api/menu", status_code=201)
def create_menu_item(item: MenuItem):
    item_id = create_document(collection_name(MenuItem), item)
    return {"id": item_id}

# Orders

class CreateOrderRequest(BaseModel):
    items: List[OrderItem]
    customer: Order.__fields__["customer"].annotation  # reuse schema
    payment_method: Order.__fields__["payment_method"].annotation = "card"

@app.post("/api/orders", status_code=201)
def create_order(payload: CreateOrderRequest):
    # Compute totals from menu prices
    menu_index = {str(doc["_id"]): doc for doc in db[collection_name(MenuItem)].find({})}
    subtotal = 0.0
    for it in payload.items:
        doc = menu_index.get(it.menu_item_id)
        if not doc:
            raise HTTPException(status_code=400, detail=f"Menu item {it.menu_item_id} not found")
        subtotal += float(doc.get("price", 0)) * it.quantity
    tax = round(subtotal * 0.08, 2)
    total = round(subtotal + tax, 2)

    order = Order(
        items=payload.items,
        customer=payload.customer,
        subtotal=round(subtotal, 2),
        tax=tax,
        total=total,
        status="created",
        payment_status="pending",
        payment_method=payload.payment_method,
    )
    oid = create_document(collection_name(Order), order)
    return {"order_id": oid, "client_secret": f"mock_{oid}", "amount": total}

@app.get("/api/orders")
def list_orders(status: Optional[str] = None):
    filt = {"status": status} if status else {}
    docs = get_documents(collection_name(Order), filt, limit=100)
    for d in docs:
        d["id"] = str(d.pop("_id", ""))
    return docs

@app.post("/api/orders/{order_id}/accept")
def accept_order(order_id: str):
    res = db[collection_name(Order)].update_one({"_id": ObjectId(order_id)}, {"$set": {"status": "accepted"}})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"status": "accepted"}

@app.post("/api/orders/{order_id}/advance")
def advance_order(order_id: str):
    pipeline = [
        "created",
        "accepted",
        "preparing",
        "ready_for_pickup",
        "out_for_delivery",
        "delivered",
    ]
    doc = db[collection_name(Order)].find_one({"_id": ObjectId(order_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Order not found")
    try:
        idx = pipeline.index(doc.get("status", "created"))
        new_status = pipeline[min(idx + 1, len(pipeline) - 1)]
    except ValueError:
        new_status = "created"
    db[collection_name(Order)].update_one({"_id": ObjectId(order_id)}, {"$set": {"status": new_status}})
    return {"status": new_status}

# Payment Webhook (mock)
@app.post("/api/payments/webhook")
def payment_webhook(order_id: str, success: bool = True):
    db[collection_name(Order)].update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"payment_status": "paid" if success else "failed"}},
    )
    return {"ok": True}

# Riders
@app.get("/api/riders")
def list_riders():
    docs = get_documents(collection_name(Rider))
    for d in docs:
        d["id"] = str(d.pop("_id", ""))
    return docs

@app.post("/api/riders", status_code=201)
def create_rider(rider: Rider):
    rid = create_document(collection_name(Rider), rider)
    return {"id": rid}

@app.post("/api/orders/{order_id}/assign/{rider_id}")
def assign_rider(order_id: str, rider_id: str):
    db[collection_name(Order)].update_one({"_id": ObjectId(order_id)}, {"$set": {"rider_id": rider_id, "status": "out_for_delivery"}})
    db[collection_name(Rider)].update_one({"_id": ObjectId(rider_id)}, {"$set": {"on_delivery": True}})
    return {"assigned": True}

# Slots / Capacity
@app.get("/api/slots")
def list_slots():
    docs = get_documents(collection_name(Slot))
    for d in docs:
        d["id"] = str(d.pop("_id", ""))
    return docs

@app.post("/api/slots", status_code=201)
def create_slot(slot: Slot):
    sid = create_document(collection_name(Slot), slot)
    return {"id": sid}

# KPIs
@app.get("/api/kpis")
def kpis():
    total_orders = db[collection_name(Order)].count_documents({})
    revenue = 0.0
    for d in db[collection_name(Order)].find({"payment_status": "paid"}):
        revenue += float(d.get("total", 0))
    open_orders = db[collection_name(Order)].count_documents({"status": {"$nin": ["delivered", "cancelled"]}})
    return {
        "total_orders": total_orders,
        "revenue": round(revenue, 2),
        "open_orders": open_orders,
    }

# Test endpoint to verify DB connectivity
@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Connected"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
            response["connection_status"] = "Connected"
            response["collections"] = db.list_collection_names()
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:80]}"
    return response

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
