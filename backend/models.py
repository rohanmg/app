from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, EmailStr, ConfigDict
import uuid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return str(uuid.uuid4())


# --- Auth ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    name: str = Field(min_length=1, max_length=80)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserPublic(BaseModel):
    id: str
    email: EmailStr
    name: str


class UserInDB(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    email: EmailStr
    name: str
    password_hash: str
    created_at: str = Field(default_factory=_now_iso)


class AuthResponse(BaseModel):
    token: str
    user: UserPublic


# --- LLD ---
class DetectedService(BaseModel):
    name: str
    category: str = "compute"
    count: int = 1
    monthly_cost_usd: float = 0.0
    unit_cost_usd: float = 0.0
    assumption: str = ""
    source: str = "curated"


class DrawioPage(BaseModel):
    id: str
    name: str
    node_count: int
    edge_count: int


class GenerateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=160)
    xml: str
    region: str = "us-east-1"


class LLD(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=_new_id)
    user_id: str
    title: str
    xml: str
    markdown: str
    services: List[DetectedService] = []
    pages: List[DrawioPage] = []
    layout: Dict[str, Any] = {}  # nodes/edges for the preview
    estimated_monthly_cost_usd: float = 0.0
    region: str = "us-east-1"
    share_token: Optional[str] = None
    is_public: bool = False
    created_at: str = Field(default_factory=_now_iso)


class LLDSummary(BaseModel):
    id: str
    title: str
    service_count: int
    estimated_monthly_cost_usd: float
    region: str = "us-east-1"
    is_public: bool = False
    created_at: str


class PublicLLD(BaseModel):
    """View-only payload returned for a shared link (no user_id / no XML if too large)."""
    id: str
    title: str
    markdown: str
    services: List[DetectedService]
    pages: List[DrawioPage]
    layout: Dict[str, Any]
    estimated_monthly_cost_usd: float
    region: str
    created_at: str
