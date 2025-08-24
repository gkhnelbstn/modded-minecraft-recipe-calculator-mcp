from pydantic import BaseModel, Field
from typing import List, Optional

class TargetItem(BaseModel):
    item: str
    qty: int = 1
    qtyCube: Optional[int] = Field(None, alias='qtyCube')

class ExtractedPlan(BaseModel):
    targets: List[TargetItem]
    notes: Optional[List[str]] = None
    warnings: Optional[List[str]] = None
