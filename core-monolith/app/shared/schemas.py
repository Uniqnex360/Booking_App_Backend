from pydantic import BaseModel
from typing import List, Generic, TypeVar
T=TypeVar("T")
class PaginationMeta(BaseModel):
    total:int
    page:int
    limit:int
    total_pages:int

class PaginatedResponse(BaseModel,Generic[T]):
    data:List[T]
    meta:PaginationMeta
    