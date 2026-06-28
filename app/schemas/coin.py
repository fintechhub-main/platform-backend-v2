import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import date

from app.models.coin import CoinTxnType


class CoinCreate(BaseModel):
    student_id: uuid.UUID
    coins: int
    txn_type: CoinTxnType = CoinTxnType.earned
    reason: Optional[str] = None
    date: date


class CoinOut(BaseModel):
    id: uuid.UUID
    student_id: uuid.UUID
    coins: int
    txn_type: CoinTxnType
    reason: Optional[str]
    date: date

    model_config = {"from_attributes": True}
