from __future__ import annotations

import uuid
from typing import Optional

from pydantic import BaseModel, Field


class FnbItemOut(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str]
    price_paise: int
    image_url: Optional[str]
    is_veg: bool
    category: str

    class Config:
        from_attributes = True


class FnbMenuOut(BaseModel):
    items: list[FnbItemOut]


class FnbLineRequest(BaseModel):
    item_id: uuid.UUID
    quantity: int = Field(ge=1, le=10)


class FnbReplaceRequest(BaseModel):
    items: list[FnbLineRequest] = Field(default_factory=list)

class FnbLineOut(BaseModel):
    item_id: uuid.UUID
    name: str
    quantity: int
    unit_price_paise: int

    class Config:
        from_attributes = True

class ContactUpdateRequest(BaseModel):
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None