from pydantic import BaseModel, ConfigDict


class Out(BaseModel):
    """Response models validate straight from document models."""

    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    total: int
