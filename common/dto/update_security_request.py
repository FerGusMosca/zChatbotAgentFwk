from pydantic import BaseModel


class UpdateSecurityRequest(BaseModel):
    security_id: int
    symbol: str | None = None
    name: str | None = None
    is_active: bool | None = None