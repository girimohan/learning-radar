from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Offer


@dataclass
class SourceResult:
    name: str
    offers: list[Offer] = field(default_factory=list)
    ok: bool = True
    error: str = ""
    detail: str = ""
    requests: int = 0
