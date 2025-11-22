"""
Database Schemas for CloudChef

Each Pydantic model represents a MongoDB collection.
Collection name is the lowercase class name.
"""
from __future__ import annotations
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Literal
from datetime import datetime

class MenuItem(BaseModel):
    title: str = Field(..., description="Dish name")
    description: Optional[str] = Field(None, description="Dish description")
    price: float = Field(..., ge=0, description="Price in dollars")
    category: Optional[str] = Field(None, description="Category like Mains, Sides, Drinks")
    is_active: bool = Field(True, description="Whether item is available to order")
    image_url: Optional[str] = Field(None, description="Image URL")

class OrderItem(BaseModel):
    menu_item_id: str = Field(..., description="Menu item ID")
    quantity: int = Field(1, ge=1)
    notes: Optional[str] = None

class CustomerInfo(BaseModel):
    name: str
    phone: str
    address: str
    email: Optional[EmailStr] = None

OrderStatus = Literal[
    "created",
    "accepted",
    "preparing",
    "ready_for_pickup",
    "out_for_delivery",
    "delivered",
    "cancelled"
]

PaymentStatus = Literal["pending", "paid", "failed", "refunded"]

class Order(BaseModel):
    items: List[OrderItem]
    customer: CustomerInfo
    subtotal: float = 0
    tax: float = 0
    total: float = 0
    status: OrderStatus = "created"
    payment_status: PaymentStatus = "pending"
    payment_method: Literal["card", "cod"] = "card"
    eta_minutes: Optional[int] = None
    rider_id: Optional[str] = None

class Rider(BaseModel):
    name: str
    phone: str
    vehicle: Optional[str] = None
    is_active: bool = True
    on_delivery: bool = False

class Slot(BaseModel):
    label: str = Field(..., description="Human readable slot like Lunch 12-3 PM")
    start_time: str = Field(..., description="24h HH:MM")
    end_time: str = Field(..., description="24h HH:MM")
    capacity: int = Field(50, ge=0)
    is_active: bool = True

# The app may also use these examples:
class User(BaseModel):
    name: str
    email: EmailStr
    address: Optional[str] = None
    is_active: bool = True

class Product(BaseModel):
    title: str
    price: float
    in_stock: bool = True
