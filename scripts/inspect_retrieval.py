"""Print retrieval scores for sample claims so you can tune MIN_RELEVANCE in config.py.

    python scripts/inspect_retrieval.py
    python scripts/inspect_retrieval.py "Your own claim here"

What to look for: claims the policies DO cover should score clearly above the
threshold; claims they DON'T cover (maternity leave) should score below it.
Set the threshold in the gap between the two groups.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402
from modules.document_loader import load_knowledge_base  # noqa: E402
from modules.evidence_retriever import EvidenceRetriever, make_embedder  # noqa: E402

COVERED = [
    "Employees can claim up to $200 per day for overseas business travel.",
    "All overseas travel claims are automatically approved.",
    "Hotels are reimbursed up to $250 per night.",
    "Travel claims must be submitted within 30 days of returning.",
    "Finance processes approved claims within 10 working days.",
]
NOT_COVERED = [
    "Employees are entitled to 16 weeks of paid maternity leave.",
    "Staff receive a 13th-month annual bonus.",
    "The bank's mortgage rate is 3.5% per year.",
]

embedder, warning = make_embedder()
if warning:
    print("WARNING:", warning)
r = EvidenceRetriever(load_knowledge_base(), embedder)
print(f"Retriever: {embedder.label}   current threshold: {config.MIN_RELEVANCE[embedder.kind]}\n")

groups = [("CUSTOM", sys.argv[1:])] if len(sys.argv) > 1 else [("COVERED", COVERED), ("NOT COVERED", NOT_COVERED)]
for name, claims in groups:
    print(f"== {name} ==")
    for claim in claims:
        top = r.search(claim)
        print(f"{top[0].score:.3f}  {claim}")
        for e in top:
            print(f"        {e.score:.3f} {e.chunk.chunk_id} {e.chunk.section_title}")
    print()
