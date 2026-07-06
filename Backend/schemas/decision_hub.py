"""Pydantic request models for api/decision_hub.py (moved out of the router)."""
from typing import Optional

from pydantic import BaseModel


class CopilotRequest(BaseModel):
    store_id: Optional[str] = None
    sub_cat:  Optional[str] = None
    cluster:  Optional[str] = None
    question: Optional[str] = ""
