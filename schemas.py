"""Pydantic request/response models, shared across routers."""
from typing import Any, List, Optional
from pydantic import BaseModel


class OpportunityIn(BaseModel):
    source: str
    title: str
    url: str
    company: Optional[str] = None
    contractor: Optional[str] = None
    industry: Optional[str] = None
    region: Optional[str] = None
    phase: Optional[str] = None
    score: int = 0
    entry: Optional[str] = None
    raw: Optional[Any] = None


class IngestPayload(BaseModel):
    items: List[OpportunityIn]


class LoginPayload(BaseModel):
    email: str
    password: str


class CreateUserPayload(BaseModel):
    email: str
    password: str
    name: Optional[str] = None


class PreferencesPayload(BaseModel):
    preferred_industries: List[str] = []
    preferred_regions: List[str] = []
    preferred_phases: List[str] = []
    preferred_companies: List[str] = []
    keywords: List[str] = []
    min_investment_usd: Optional[int] = None
    weight_region: float = 1.0
    weight_industry: float = 1.0
    weight_investment: float = 1.0
    weight_phase: float = 1.0
    weight_company: float = 1.0


class ContactIn(BaseModel):
    name: str
    company: str
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None


class ContactUpdate(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    notes: Optional[str] = None


class PipelineUpdate(BaseModel):
    status: str
    assignee: Optional[str] = None


class NoteIn(BaseModel):
    note: str
    author: Optional[str] = None


class ServiceItem(BaseModel):
    name: str
    description: Optional[str] = None


class ServiceProfilePayload(BaseModel):
    company_name: Optional[str] = None
    company_key: Optional[str] = None
    services: List[Any] = []        # acepta strings o {name, description}
    regions: List[str] = []
    contract_sizes: List[str] = []
    known_mandantes: List[str] = []
    onboarding_done: bool = False
