"""Pydantic request models for api/agents.py (moved out of the router)."""
from typing import Optional

from pydantic import BaseModel


class WatchdogNarrativeRequest(BaseModel):
    store_id: Optional[str] = None
    sub_cat:  Optional[str] = None
    cluster:  Optional[str] = None
    top_n:    int = 10


class OverrideRequest(BaseModel):
    sku_id:      str
    cluster_id:  str
    decision:    str           # "approved" | "rejected"
    note:        Optional[str] = ""
    decided_by:  Optional[str] = "Category Manager"


class BriefRequest(BaseModel):
    brief_type:   str
    brand:        Optional[str]      = None
    sub_cat:      Optional[str]      = None
    sku_ids:      Optional[list]     = None
    generated_by: Optional[str]      = "Category Manager"
