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
    family: str = ""       # all versions of one policy share a family, e.g. "TRAVEL_POLICY"
    expiry_date: str | None = None
    applies_to: str = ""   # who/what the policy covers (from the document header)

    def embedding_text(self) -> str:
        # Prefixing the doc + section title gives the embedder context the body
        # lacks, e.g. "up to $150 per day" alone doesn't say "travel allowance".
        return f"{self.document_title} — {self.section} {self.section_title}: {self.text}"


@dataclass
class Claim:
    claim_id: int
    claim: str
    # Filled by the extraction check: problems with how the AI rewrote the answer
    extraction_warnings: list[str] = field(default_factory=list)


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
    applicability: str = ""            # step 1: does this policy apply to the situation?
    policy_requirement: str = ""       # step 4: what the policy requires, derived before judging
    derivation: list[dict] = field(default_factory=list)  # the five "how we get the answer" steps
    root_cause: str = ""               # e.g. "matches superseded v2.1" (contradictions only)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RequiredElement:
    """One fact or step the policy says a correct answer to THIS question must include."""
    element: str
    covered: bool
    source_id: str = ""
    source_title: str = ""
    section: str = ""
    section_title: str = ""
    version: str = ""
    quote: str = ""
    note: str = ""
    essential: bool = True             # False = useful extra detail, not needed to act correctly


@dataclass
class CompletenessResult:
    checked: bool = False              # False when there was no relevant policy to check against
    elements: list[RequiredElement] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)  # elements discarded by the quote check

    @property
    def missing(self) -> list[RequiredElement]:
        """Only ESSENTIAL gaps make an answer incomplete."""
        return [e for e in self.elements if not e.covered and e.essential]

    @property
    def extra_details(self) -> list[RequiredElement]:
        return [e for e in self.elements if not e.covered and not e.essential]

    def to_dict(self) -> dict:
        return {"checked": self.checked, "elements": [asdict(e) for e in self.elements],
                "missing": [e.element for e in self.missing],
                "extra_details": [e.element for e in self.extra_details], "dropped": self.dropped}


@dataclass
class CorrectionSentence:
    text: str
    source_id: str = ""
    section: str = ""
    quote: str = ""
    # Filled by re-verification (A citation, B rules table, C entailment)
    checks: dict = field(default_factory=dict)


@dataclass
class Correction:
    status: str                        # "suggested" | "no_evidence" | "not_needed" | "failed"
    message: str = ""
    sentences: list[CorrectionSentence] = field(default_factory=list)
    reverification: str = ""           # "confirmed" | "partially_confirmed" | "not_confirmed" | ""
    reverification_note: str = ""

    @property
    def text(self) -> str:
        return " ".join(s.text for s in self.sentences)

    def to_dict(self) -> dict:
        return {"status": self.status, "message": self.message, "text": self.text,
                "sentences": [asdict(s) for s in self.sentences],
                "reverification": self.reverification, "reverification_note": self.reverification_note}


@dataclass
class AgentHandoff:
    """What Agent 1 passes to TrustGuard: the data contract between the two agents.

    TrustGuard verifies ONLY `question` + `answer`. Agent 1's own `sources` are kept
    for the audit trail but are never used as evidence: if the assistant read an
    outdated document, trusting its citations would let the same mistake pass twice.
    TrustGuard always does its own search over approved documents instead."""
    question: str
    answer: str
    agent_name: str          # "Banking AI Assistant"
    model: str               # which LLM Agent 1 used
    kb_scope: str            # "all" | "approved" | "none"
    sources: list[dict] = field(default_factory=list)  # passages Agent 1 says it used
    created_at: str = ""     # ISO timestamp of the handoff
    latency_s: float = 0.0   # how long Agent 1 took to answer

    def to_dict(self) -> dict:
        return asdict(self)
