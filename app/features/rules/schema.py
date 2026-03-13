from pydantic import BaseModel


class RuleCreate(BaseModel):
    name: str
    engine: str
    frequency: str = "As It Occurs"
    channel: str = "In-App"
    targets: list[str] = []
    params: dict = {}
    description: str = ""
    expiry_date: str | None = None


class RuleUpdate(BaseModel):
    name: str | None = None
    engine: str | None = None
    frequency: str | None = None
    channel: str | None = None
    targets: list[str] | None = None
    params: dict | None = None
    description: str | None = None
    expiry_date: str | None = None


class RuleToggle(BaseModel):
    enabled: bool
