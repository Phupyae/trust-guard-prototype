"""Shared data formats. Every module speaks these types, so modules can be built
and tested separately and still plug together (Part E of the project plan)."""
from dataclasses import asdict, dataclass, field

SUPPORTED = "SUPPORTED"
CONTRADICTED = "CONTRADICTED"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
STATUSES = (SUPPORTED, CONTRADICTED, INSUFFICIENT_EVIDENCE)


@dataclass
class Chunk:
    """One numbered section of one policy document — the unit we retrieve and cite."""
    chunk_id: str          # e.g. "TRAVEL_POLICY_V2::4.2"
    document_id: str
    document_title: str
    version: str
    status: str
    effective_date: str
    section: str           # "4.2"
    section_title: str     # "Daily Allowance"
    text: str              # body text only

    def embedding_text(self) -> str:
        # Prefixing the doc + section title gives the embedder context the body
        # lacks, e.g. "up to $150 per day" alone doesn't say "travel allowance".
        return f"{self.document_title} — {self.section} {self.section_title}: {self.text}"


@dataclass
class Claim:
    claim_id: int
    claim: str


@dataclass
class Evidence:
    chunk: Chunk
    score: float


@dataclass
class VerificationResult:
    """Matches the JSON contract in the project plan, plus a few extra fields."""
    claim_id: int
    claim: str
    status: str
    explanation: str
    evidence: str = ""                 # the exact sentence(s) relied on
    source_id: str = ""
    source_title: str = ""
    section: str = ""
    section_title: str = ""
    version: str = ""
    retrieval_score: float = 0.0
    rule_checks: list[str] = field(default_factory=list)
    needs_review: bool = False
    retrieved: list[dict] = field(default_factory=list)  # all top-k passages, for transparency

    def to_dict(self) -> dict:
        return asdict(self)
