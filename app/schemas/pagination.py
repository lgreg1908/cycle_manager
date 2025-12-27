from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    """Pagination metadata"""
    total: int
    limit: int
    offset: int
    has_more: bool

    @property
    def page(self) -> int:
        """Calculate current page number (1-indexed)"""
        if self.limit == 0:
            return 1
        return (self.offset // self.limit) + 1

    @property
    def total_pages(self) -> int:
        """Calculate total number of pages"""
        if self.limit == 0:
            return 1
        return (self.total + self.limit - 1) // self.limit


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper"""
    items: list[T]
    pagination: PaginationMeta

