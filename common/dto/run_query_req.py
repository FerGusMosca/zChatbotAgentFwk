from pydantic import BaseModel


class RunQueryReq(BaseModel):
    run_id: int
    portfolio: str
    source: str
    year: int
    tag_name: str
    query: str