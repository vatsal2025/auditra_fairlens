from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class ColumnInfo(BaseModel):
    name: str
    dtype: str          # "numeric" | "categorical"
    unique_count: int
    null_pct: float


class UploadResponse(BaseModel):
    session_id: str
    columns: List[ColumnInfo]
    row_count: int


class AuditRequest(BaseModel):
    session_id: str
    protected_attributes: List[str]
    max_depth: int = 4
    threshold: float = 0.15


class ChainHop(BaseModel):
    source: str
    target: str
    weight: float       # correlation / predictive strength 0-1


class Chain(BaseModel):
    id: str
    path: List[str]
    hops: List[ChainHop]
    risk_score: float   # 0-1, reconstructive accuracy
    risk_label: str     # LOW | MEDIUM | HIGH | CRITICAL
    protected_attribute: str
    explanation: Optional[str] = None
    weakest_link: Optional[str] = None


class GraphNode(BaseModel):
    id: str
    label: str
    dtype: str
    is_protected: bool
    risk_level: str     # none | low | medium | high | critical


class GraphEdge(BaseModel):
    source: str
    target: str
    weight: float


class AuditResponse(BaseModel):
    session_id: str
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    chains: List[Chain]
    summary: str


class FixRequest(BaseModel):
    session_id: str
    chain_id: str


class ShapEntry(BaseModel):
    feature: str
    before: float
    after: float


class FixResponse(BaseModel):
    session_id: str
    chain_id: str
    removed_feature: str
    shap_values: List[ShapEntry]
    success: bool
    message: str


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatResponse(BaseModel):
    reply: str


class ReportRequest(BaseModel):
    session_id: str


class ReportResponse(BaseModel):
    download_url: str
