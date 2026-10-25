# TrustGuard AI — Working Prototype

**OCBC Ignite Innovation Challenge 2026 · Problem Statement 1: Trusted AI Agents**
Team: Abby, Maria & Phu

TrustGuard checks an AI assistant's answer against approved policy documents, **one factual claim at a time**, and labels each claim **SUPPORTED**, **CONTRADICTED** or **INSUFFICIENT_EVIDENCE**, with the exact evidence and section it relied on.

> All policy documents are fictional ("Northbridge Bank"). No real OCBC data is used.

---

## Quick start

```bash
git clone https://github.com/Phupyae/trust-guard-prototype.git
cd trust-guard-prototype
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # Windows: copy .env.example .env
# open .env and paste your GEMINI_API_KEY (free) or set LLM_PROVIDER=claude + ANTHROPIC_API_KEY

streamlit run app.py
```

The first run downloads the embedding model (~90 MB) from Hugging Face. After that, retrieval works offline.

| Command | What it does |
|---|---|
| `streamlit run app.py` | The demo dashboard |
| `pytest -q` | 13 offline tests (no API key needed) |
| `python tests/run_eval.py` | Runs every labelled case through the **real** pipeline and prints accuracy |
| `python scripts/inspect_retrieval.py` | Shows retrieval scores so you can tune the relevance threshold |
| `python scripts/build_pdfs.py` | Rebuilds the policy PDFs after editing `knowledge_base/source/*.md` |

---

## How it works

```
Employee question + AI answer
        │
        ▼
1. Claim extraction        LLM (forced tool call → guaranteed JSON)
        │                  "You can claim $200/day; auto-approved" → 2 claims
        ▼
2. Evidence retrieval      Sentence-Transformers embeddings + cosine similarity
        │                  over numbered policy sections (approved docs only)
        ▼
3. Hybrid verification     LLM judges meaning  ─┐
        │                  Python rules check  ─┴→ rules can only make it MORE cautious
        │                  numbers / requirements / quotes
        ▼
4. Dashboard               Status · explanation · exact quote · document, version, section
```

### Module guide (what each file does and *why*)

| File | Role | The key design decision |
|---|---|---|
| `modules/document_loader.py` | Reads the PDFs with PyMuPDF and splits them into numbered sections | A line counts as a heading only if it is **bold and numbered**, so body text like "30 calendar days" is never mistaken for one. Each section is one rule and carries its own citation. |
| `modules/claim_extractor.py` | Splits the answer into atomic, self-contained claims | Claims must be **self-contained** ("All *travel* claims…", not "They…") because each one is later used alone as a search query. |
| `modules/llm_client.py` | One interface for "ask the LLM, get JSON back" | Uses a **forced tool call** with a JSON schema, so the reply can't contain broken JSON. Swapping provider means changing one class. |
| `modules/evidence_retriever.py` | Finds the top-3 most relevant sections per claim | Embeddings match **meaning** rather than words. There's no vector DB because 30 sections take microseconds to search. **Superseded** documents are excluded from search. Falls back to TF-IDF if the model can't load. |
| `modules/claim_verifier.py` | LLM judgement and rule checks → final status | If nothing relevant is retrieved, the result is INSUFFICIENT_EVIDENCE **without calling the LLM**, so it can't "find" support in unrelated text. |
| `modules/policy_rules.py` | Deterministic checks | Numbers and units, "not required" vs "required", and whether the quote really exists in the source. Rules **never upgrade** a verdict; a disagreement downgrades it and flags it for human review. |
| `modules/pipeline.py` | Glue and the overall verdict | The most severe claim decides the headline, because one wrong fact makes an answer unsafe to act on. |
| `app.py` | Streamlit UI | Shows each pipeline stage live. Never shows a raw traceback. |

### Shared data contract
Every verified claim produces the JSON agreed in the project plan (plus extras such as `rule_checks` and `needs_review`):
```json
{"claim_id": 1, "claim": "Employees can claim up to $200 per day for overseas business travel.",
 "status": "CONTRADICTED", "evidence": "Employees may claim up to $150 per day for eligible overseas business travel expenses.",
 "source_id": "TRAVEL_POLICY_V2", "section": "4.2", "explanation": "The policy sets the daily allowance at $150, not $200."}
```

### Knowledge base
| Document | Status | Why it's there |
|---|---|---|
| `TRAVEL_POLICY_V2` Employee Overseas Business Travel Policy v2.0 | Approved | Main demo source ($150/day, manager approval, 30-day deadline) |
| `SOP_FIN_012` Staff Expense Claims SOP v1.3 | Approved | Procedural steps; ready for the future completeness check |
| `TRAVEL_POLICY_V1` v1.0 | **Superseded** | Old figures ($120/day, 60 days). Excluded from search, so an AI that repeats outdated rules gets caught (test case E) |

Source files live in `knowledge_base/source/*.md` and are published as PDFs, mirroring how real policies are authored and then distributed as controlled PDFs. Metadata (version, status, dates) lives in `policy_metadata.json`, as it would in a document management system.

---

## Honest limitations (say these before the judges do)
- A **SUPPORTED** claim is supported by the *available approved evidence*. That is not a guarantee of truth.
- The rules are deliberately simple and catch common, high-impact errors only: amounts, durations, approval and receipts.
- Accuracy is measured on our own small labelled set (`tests/test_cases.json`). Quote the `run_eval.py` result, not a guess.
- Completeness ("the answer left out a step"), correction and reverification are **Phase 2 proposals**, not built yet.

## Configuration (`.env`)
| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini` (free tier), `claude` (paid), or `mock` = offline heuristics for development only (the UI shows a purple warning) |
| `GEMINI_API_KEY` | — | Free from aistudio.google.com. Free-tier prompts may be used by Google for training, which is fine for our fictional data but means no real data should ever go in |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Flash-Lite has a larger free daily allowance than Flash |
| `ANTHROPIC_API_KEY` | — | From console.anthropic.com (billed separately from a Claude subscription) |
| `CLAUDE_MODEL` | `claude-haiku-5-5` | Switch to `claude-sonnet-5-5` if verification quality isn't good enough |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Small and fast; runs on a laptop CPU |
