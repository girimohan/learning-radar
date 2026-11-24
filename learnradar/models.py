from __future__ import annotations

from dataclasses import dataclass, field

# What kind of thing an offer is. Shown on the dashboard in this order.
KINDS = {
    "degree": "Degree",
    "vocational": "Vocational qualification",
    "training": "Professional training",
    "course": "Course",
    "online": "Online course",
    "certification": "Certification",
    "prep": "Language & preparatory",
}

# What it costs the learner.
COSTS = {
    "free": "Free",
    "funded": "Free (publicly funded)",
    "free_eu": "Free for EU/EEA citizens",
    "audit": "Free to learn, certificate paid",
    "varies": "Free or paid, depends on the option",
    "paid": "Paid",
    "unknown": "Cost not stated",
}

# Why someone is looking. An offer can serve several goals.
GOALS = {
    "upskill": "Upskill in my job",
    "change": "Change career",
    "degree": "Get a degree",
    "learn": "Learn something new",
}


@dataclass
class Offer:
    """One course, training programme, degree or certification from one source."""
    source: str                     # "opintopolku", "daad", "futurelearn", "coursera", "mslearn", "moocfi"
    source_id: str
    title: str
    url: str
    provider: str = ""
    country: str = ""               # "Finland", "Germany", or "" for online-only offers
    city: str = ""
    kind: str = "course"            # a key of KINDS
    level: str = ""                 # bachelor, master, doctorate, beginner, intermediate, advanced
    cost: str = "unknown"           # a key of COSTS
    cost_note: str = ""
    languages: list[str] = field(default_factory=list)   # ISO codes: en, fi, sv, de
    online: bool = False
    self_paced: bool = False
    credits: float | None = None    # ECTS
    duration: str = ""
    starts: str = ""                # ISO date (YYYY-MM-DD) when known, otherwise free text
    deadline: str = ""              # ISO date (YYYY-MM-DD) when known
    status: str = ""                # open (apply now), upcoming (opens soon), anytime (start any time), scheduled
    tags: list[str] = field(default_factory=list)        # jotpa, unemployed, continuing, micro, open_university...
    subjects: list[str] = field(default_factory=list)    # the source's own subject labels
    summary: str = ""
    group: str = ""                 # a sub-list within the source (e.g. Swedish school type), for caps
    # Filled in by the pipeline
    topic: str = ""
    topics: list[str] = field(default_factory=list)
    topic_weight: float = 0.0
    goals: list[str] = field(default_factory=list)
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    first_seen: str = ""
    is_new: bool = False
    closing_soon: bool = False

    @property
    def uid(self) -> str:
        return f"{self.source}:{self.source_id}"

    def text(self) -> str:
        return f"{self.title} {' '.join(self.subjects)} {self.summary}".lower()

    def to_public(self) -> dict:
        d = {
            "id": self.uid, "source": self.source, "title": self.title, "url": self.url, "provider": self.provider,
            "country": self.country, "city": self.city, "kind": self.kind, "level": self.level, "cost": self.cost,
            "cost_note": self.cost_note, "languages": self.languages, "online": self.online,
            "self_paced": self.self_paced, "credits": self.credits, "duration": self.duration, "starts": self.starts,
            "deadline": self.deadline, "status": self.status, "tags": self.tags, "topic": self.topic,
            "topics": self.topics, "goals": self.goals, "score": round(self.score, 1), "reasons": self.reasons,
            "first_seen": self.first_seen, "is_new": self.is_new, "closing_soon": self.closing_soon,
            "summary": self.summary[:220],
        }
        # Leave out empty values: the file is read by every visitor's browser.
        return {k: v for k, v in d.items() if v not in ("", None, [], False) or k in ("score",)}
