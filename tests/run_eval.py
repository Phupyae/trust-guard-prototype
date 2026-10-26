"""Run every labelled case in test_cases.json through the REAL pipeline and score it.

    python tests/run_eval.py            # uses LLM_PROVIDER from .env (claude)
    python tests/run_eval.py --mock     # offline plumbing check only

This produces the numbers you can honestly quote ("x of y claims classified
correctly on our labelled set"), instead of claiming accuracy without evidence.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.document_loader import load_knowledge_base  # noqa: E402
from modules.evidence_retriever import EvidenceRetriever, make_embedder  # noqa: E402
from modules.llm_client import get_client  # noqa: E402
from modules.pipeline import run_pipeline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true", help="use the offline mock LLM")
    parser.add_argument("--tfidf", action="store_true", help="use the TF-IDF fallback retriever")
    args = parser.parse_args()

    cases = json.loads((Path(__file__).parent / "test_cases.json").read_text(encoding="utf-8"))["cases"]
    embedder, warning = make_embedder("tfidf" if args.tfidf else "sentence-transformers")
    if warning:
        print("WARNING:", warning)
    retriever = EvidenceRetriever(load_knowledge_base(), embedder)
    llm = get_client("mock") if args.mock else get_client()
    print(f"LLM: {llm.name}   Retriever: {embedder.label}\n")

    correct = total = 0
    for case in cases:
        report = run_pipeline(case["question"], case["answer"], retriever, llm)
        got = [r.status for r in report.results]
        exp = case["expected"]
        print(f"■ {case['label']}")
        if len(got) != len(exp):
            print(f"  ! extracted {len(got)} claims, expected {len(exp)} — compare by hand:")
        for i, r in enumerate(report.results):
            e = exp[i] if i < len(exp) else "?"
            ok = r.status == e
            correct += ok
            total += 1
            print(f"  {'✓' if ok else '✗'} {r.status:22} (expected {e:22}) {r.claim}")
            if not ok:
                print(f"      why: {r.explanation}")
        print()
    print(f"Claim-level accuracy: {correct}/{total} = {correct / max(total, 1):.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
