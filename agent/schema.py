"""
schema.py
---------
The strict output contract the agent extracts for every app.
Using a schema (not free text) is what makes 100 rows comparable and lets the
verification loop diff first-pass vs. verified answers field-by-field.
"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Access(str, Enum):
    self_serve = "self-serve"   # a dev can get working credentials free / on a trial
    partial = "partial"         # sandbox self-serve, but production needs approval/paid plan
    gated = "gated"             # needs partnership / contact-sales / enterprise account
    unknown = "unknown"


class Verdict(str, Enum):
    easy = "easy"               # self-serve auth + broad documented API -> ship a toolkit now
    buildable = "buildable"     # doable, but a real blocker (auth setup, plan, review) exists
    gated = "gated"             # cannot build without a commercial/partner conversation
    needs_human = "needs-human" # agent could not confirm -> escalate


class MCP(str, Enum):
    yes = "yes"                 # official/first-party MCP server
    community = "community"     # credible community MCP exists
    no = "no"
    unknown = "unknown"


class AppResearch(BaseModel):
    id: int
    name: str
    website: str
    category: str
    one_liner: str = Field(..., description="What it does, one line.")
    auth: str = Field(..., description="Primary auth method(s): OAuth2, API key, Basic, token, HMAC, none.")
    self_serve: Access
    serve_note: str = Field(..., description="How a developer actually gets credentials.")
    api_surface: str = Field(..., description="REST/GraphQL, rough breadth, notable endpoints.")
    mcp: MCP
    verdict: Verdict
    blocker: str = Field("", description="Main blocker to building a toolkit today ('' if none).")
    evidence: str = Field(..., description="Docs URL behind the answer.")
    confidence: str = Field(..., description="high | medium | low — the agent's self-report.")

    # Provenance / verification
    verified: bool = False
    first_pass: Optional[dict] = None  # snapshot of fields the verification loop changed
