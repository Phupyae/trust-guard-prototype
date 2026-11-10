# TrustGuard AI — Working Prototype

**OCBC Ignite Innovation Challenge 2026 · Problem Statement 1: Trusted AI Agents**
Team: Abby, Maria & Phu

**Two agents.** An employee asks a question. **Agent 1, the Banking AI Assistant**, writes an answer. **Agent 2, TrustGuard**, intercepts that answer before the employee sees it and checks it against approved policy documents. The employee gets the answer together with the verdict and evidence.

TrustGuard checks the assistant's answer against approved policy documents, **one factual claim at a time**, and labels each claim **SUPPORTED**, **CONTRADICTED** or **INSUFFICIENT_EVIDENCE**, with the exact evidence and section it relied on.

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
| `pytest -q` | 18 offline tests (no API key needed) |
| `python tests/run_eval.py` | Runs every labelled case through the **real** pipeline and prints accuracy |
| `python scripts/inspect_retrieval.py` | Shows retrieval scores so you can tune the relevance threshold |
| `python scripts/build_pdfs.py` | Rebuilds the policy PDFs after editing `knowledge_base/source/*.md` |

---

## How it works

```
Employee question
        │
        ▼
0. Agent 1 answers         Banking AI Assistant: its own search index + LLM
        │                  → AgentHandoff {question, answer, model, sources it read}
        ▼  (answer is held: the employee doesn't see it yet)
TrustGuard receives question + answer only. It never trusts Agent 1's sources.
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
| `modules/banking_assistant.py` | **Agent 1**: an ordinary retrieval-augmented assistant | Never told to make mistakes. It is set up the way a typical deployed chatbot is: a **bulk-loaded index** (superseded v1 policy and an unofficial team FAQ, with no version labels), the provider's **smallest model**, and only **2 passages** per question. Every error it makes comes from one of those realistic settings. It has its own index, separate from TrustGuard's. |
| `modules/document_loader.py` | Reads the PDFs with PyMuPDF and splits them into numbered sections | A line counts as a heading only if it is **bold and numbered**, so body text like "30 calendar days" is never mistaken for one. Each section is one rule and carries its own citation. |
| `modules/claim_extractor.py` | Splits the answer into atomic, self-contained claims | Claims must be **self-contained** ("All *travel* claims…", not "They…") because each one is later used alone as a search query. |
| `modules/llm_client.py` | One interface for "ask the LLM, get JSON back" | Uses a **forced tool call** with a JSON schema, so the reply can't contain broken JSON. Swapping provider means changing one class. |
| `modules/evidence_retriever.py` | Finds the top-3 most relevant sections per claim | Embeddings match **meaning** rather than words. There's no vector DB because 30 sections take microseconds to search. **Superseded** documents are excluded from search. Falls back to TF-IDF if the model can't load. |
| `modules/claim_verifier.py` | LLM judgement and rule checks → final status | If nothing relevant is retrieved, the result is INSUFFICIENT_EVIDENCE **without calling the LLM**, so it can't "find" support in unrelated text. |
| `modules/policy_rules.py` | Deterministic checks | Numbers and units, "not required" vs "required", whether the quote really exists in the source, and two **extraction checks** that guard the extractor AI (a claim must not contain numbers the answer never said; every number in the answer must appear in some claim). Rules **never upgrade** a verdict; a disagreement downgrades it and flags it for human review. |
| `modules/pipeline.py` | Glue and the overall verdict | `run_two_agent()` = Agent 1 → handoff → TrustGuard. The most severe claim decides the headline, because one wrong fact makes an answer unsafe to act on. |
| `app.py` | Streamlit UI | A chat with **Agent 1**, the product the employee uses. After each answer, **TrustGuard steps into the chat as a second agent**: "Answer intercepted", live checking, then the verdict, which is also stamped back onto the assistant's answer. Never shows a raw traceback. |

### Shared data contract
Every verified claim produces the JSON agreed in the project plan (plus extras such as `rule_checks` and `needs_review`):
```json
{"claim_id": 1, "claim": "Employees can claim up to $200 per day for overseas business travel.",
 "status": "CONTRADICTED", "evidence": "Employees may claim up to $150 per day for eligible overseas business travel expenses.",
 "source_id": "TRAVEL_POLICY_V2", "section": "4.2", "explanation": "The policy sets the daily allowance at $150, not $200."}
```

### Agent 1 → TrustGuard handoff (`AgentHandoff` in `schemas.py`)
```json
{"question": "...", "answer": "...", "agent_name": "Banking AI Assistant", "model": "gemini-3.5-flash-lite",
 "kb_scope": "all", "sources": [{"source_id": "TRAVEL_POLICY_V1", "section": "4.2", "status": "Superseded"}],
 "created_at": "2026-11-10T13:00:00+00:00", "latency_s": 2.1}
```
TrustGuard verifies only `question` + `answer`. `sources` is kept for the audit trail (the UI shows it under "What the assistant read"). It is not used as evidence, because if the assistant read the wrong document, trusting its citations would let the same mistake through twice.

Example questions for the demo are in `knowledge_base/demo_questions.json`. Agent 1 writes the answers live, so results can differ between runs. The fixed answers in `tests/test_cases.json` are still used by `run_eval.py` to measure TrustGuard on its own.

### Simulation assumptions (state these in the presentation)
1. **TrustGuard connects to the bank's governed policy repository**: approved documents only, each with an owner, version, status and effective date.
2. **Agent 1 uses a broad, uncontrolled knowledge base**, as deployed chatbots usually do: policies, old versions and intranet pages loaded in bulk.
3. **Agent 1 is tuned for cost and speed** (smallest model, few passages), because it serves every employee.
4. Nothing tells Agent 1 to be wrong. To show TrustGuard's value doesn't depend on a messy index, run the same questions with `AGENT1_KB_SCOPE=approved` too (clean sources, so only the model's own mistakes remain) and report both.

### Knowledge base
| Document | Status | Why it's there |
|---|---|---|
| `TRAVEL_POLICY_V2` Employee Overseas Business Travel Policy v2.0 | Approved | Main demo source ($150/day, manager approval, 30-day deadline) |
| `SOP_FIN_012` Staff Expense Claims SOP v1.3 | Approved | Procedural steps; ready for the future completeness check |
| `INTRANET_TRAVEL_FAQ` team intranet page | **Unofficial** | Written by a sales team in 2024, not a policy owner. Mixes outdated figures ($120/day, ~2 months), over-generalisations (receipts for everything), dropped conditions (business class without approval) and wrong rules (laundry from 3 days). TrustGuard never searches it; Agent 1 can read it when `AGENT1_KB_SCOPE=all` |
| `TRAVEL_POLICY_V1` v1.0 | **Superseded** | Old figures ($120/day, 60 days). TrustGuard never searches it. Agent 1 can read it when `AGENT1_KB_SCOPE=all`, which is how it realistically gives outdated answers (also test case E) |

Source files live in `knowledge_base/source/*.md` and are published as PDFs, mirroring how real policies are authored and then distributed as controlled PDFs. Metadata (version, status, dates) lives in `policy_metadata.json`, as it would in a document management system.

---

## Interface design
The dashboard (`app.py`) is built around five usability principles:

| Principle | How the interface applies it |
|---|---|
| Perceivability | Every status is an icon, a word and a colour (never colour alone). Each claim sits side by side with the policy text it was checked against, so a contradiction is visible at a glance. Policy text is set in a serif face, so document text always looks different from interface text. |
| Predictability | The chat always follows the same order: your question → Agent 1's answer (marked "Intercepted by TrustGuard") → TrustGuard's check → verdict badge on the answer. Each message is labelled with the agent that wrote it. |
| Learnability | Plain-language help under each step and on each input, plus a status key next to the findings. |
| Feedback | Loading message while the model starts, live progress (claims found, then checking), a completion toast, a notice when the inputs no longer match the results, and errors that say what to do. |
| Consistency | One status vocabulary (✓ Supported, ✕ Contradicted, ? Insufficient evidence, ! Needs review) used in the verdict, the key, the cards and the sidebar. |

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
| `AGENT1_MODEL` | *(empty)* | Agent 1's model. Empty = the provider's smallest model (`gemini-3.5-flash-lite` / `claude-haiku-5-5`) |
| `AGENT1_KB_SCOPE` | `all` | What Agent 1 can read: `all` (incl. superseded policy and unofficial FAQ, no version labels), `approved`, or `none` (general knowledge only) |
| `AGENT1_TOP_K` | `2` | Passages Agent 1 reads per question |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Small and fast; runs on a laptop CPU |
