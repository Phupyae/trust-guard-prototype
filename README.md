# TrustGuard AI — Working Prototype (up to Priority 2)

**OCBC Ignite Innovation Challenge 2026 · Problem Statement 1: Trusted AI Agents**
Team: Abby, Maria & Phu

**Two agents, one policy repository.** An employee types a question. **Agent 1, the Banking AI Assistant**, answers it quickly on a cheaper model. **TrustGuard** intercepts the answer before the employee relies on it. It doesn't just say "right" or "wrong": it **shows how the right answer is reached from the policy in effect** (which policy, which version, which rule, what the rule says), compares that with Agent 1's answer, checks nothing required is missing, suggests an evidence-backed correction, and **re-checks its own correction with independent methods**.

> All policy documents are **synthetic** ("Northbridge Bank" is fictional) and every page is marked *SYNTHETIC DEMONSTRATION DOCUMENT - NOT OCBC POLICY*. No real OCBC data is used.

---

## Quick start

```bash
git clone https://github.com/Phupyae/trust-guard-prototype.git
cd trust-guard-prototype
python -m venv .venv
# Windows: .venv\Scripts\activate     macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # Windows: copy .env.example .env   then paste your GEMINI_API_KEY
streamlit run app.py
```

The first run downloads two small models from Hugging Face: the search model (~90 MB) and the entailment model for re-checking corrections (~280 MB). After that they work offline.

| Command | What it does |
|---|---|
| `streamlit run app.py` | The demo |
| `pytest -q` | 63 offline tests (no API key needed) |
| `python eval/run_eval.py --live` | Live evaluation: Agent 1 answers, TrustGuard checks, files to label (see `eval/README.md`) |
| `python eval/run_eval.py --controlled` | Regression check on fixed answers with known labels |
| `python eval/compute_metrics.py eval/results/<folder>` | Metrics from a labelled run |
| `python scripts/build_pdfs.py` | Rebuild policy PDFs after editing `knowledge_base/source/*.md` |

---

## What changed after mentoring (and why)

| Mentor feedback | What we built |
|---|---|
| Both agents should use the **same trusted source** | Both read the **same governed policy repository**. The unofficial FAQ page is gone. |
| Two different **models** are fine: cheap for Agent 1, strong for TrustGuard | `AGENT1_MODEL` (default `gemini-3.1-flash-lite`, older generation) and `TRUSTGUARD_MODEL` (default `gemini-3.5-flash-lite`, newer generation), same provider. Both fit the free tier. With a paid key set `TRUSTGUARD_MODEL=gemini-3.8-flash` for a full tier split. The app warns if they're the same. |
| TrustGuard should **explain the in-between steps** ("1 + 1 = 2 because two fingers"), not re-confirm the answer | Every claim gets a 5-step derivation: ① policy that applies → ② version in effect → ③ rule matched → ④ what the rule says (worked out **before** judging) → ⑤ result. |
| Two **modes**: daily (show only when there's a problem) and always-explain | Sidebar toggle: **Daily mode** (✓ badge, "Show how" one click away, issues open automatically) and **Audit mode** (every step always shown). |
| Employees should **type questions**, with handling of edge-case inputs | Free-text chat with two layers of input checks (below). Example questions only fill the box; Agent 1 always answers live. |
| Don't rely on **pre-written answers** | The main evaluation uses **live** Agent 1 answers. A small set of fixed answers is kept only as a regression check and reported separately. |

### Why is Agent 1 weaker? (assumptions to state in the presentation)
1. **Volume, cost and deployment lag.** Agent 1 answers every question from every employee, so banks run assistants like it on fast, cheap models, and the assistant already in production usually runs an **older** model because every model change must pass model-risk review. TrustGuard runs once per answer and can use a newer, stronger model (and could later be limited to high-risk topics). The prototype uses an older vs newer Flash-Lite generation to stay within the free tier; in production the gap would be a full tier.
2. **Same source, read differently.** Both read the same repository, which, like any document management system, keeps superseded versions. Agent 1 indexes the text only and reads its top 2 passages. TrustGuard filters by version and effective date **in code**, reads whole rule groups (e.g. all amount bands of §3), and searches with the question as well as the claim.
3. **Maker-checker.** Banks don't let the person who prepares a transaction approve it. Agent 1 is the maker and TrustGuard the checker. A model checking its own answer is self-approval.
4. **Works with an existing assistant.** TrustGuard only needs `question + answer`, so it can sit on top of an assistant the bank already runs without replacing it.
5. **Nothing tells Agent 1 to be wrong.** Its mistakes come from the realistic settings above. To show TrustGuard isn't "just the stronger model", the evaluation includes an **ablation** with TrustGuard on the *cheap* model too.

---

## How it works

```
Employee types a question
   │  Input checks, layer 1 (code): empty / too long / gibberish / greeting / prompt injection /
   │     personal data masked (NRIC, card, account, phone, email) / rate limit
   │  Input checks, layer 2 (Agent 1's cheap model): in scope · small talk · off topic · unclear
   │     (asks a clarifying question) · action request · translates non-English/Singlish
   ▼
Agent 1 answers live (cheap model, top-2 passages, no version filtering, no citations shown)
   ▼  answer held: "Intercepted by TrustGuard"
TrustGuard (strong model)
 0. Policy validation   as-of date = today, or the date in the question ("in 2025") → which versions are in effect (code)
 1. Claim extraction    the answer → atomic, self-contained claims
 2. Evidence retrieval  per claim: search policies IN EFFECT with the claim AND the question, plus sibling rules
 3. Verification        per claim: ①–⑤ derivation → SUPPORTED / CONTRADICTED / INSUFFICIENT_EVIDENCE
                        + code rules (numbers, requirements, quote exists, version in effect) that can only make
                          a verdict more cautious
                        + root cause (code): "this matches superseded v2.1 §3.2"
 4. Completeness        from the POLICY side: facts/steps a correct answer must include → which are missing
 5. Correction          if anything is wrong or missing: suggested answer, every sentence citing a quote
 6. Re-verification     the correction is checked by methods that don't depend on the LLM that wrote it:
                          A citation (code)   quote exists word for word, version in effect, no new numbers
                          B rules table (code) amounts, approvers, required/not required vs knowledge_base/rules/
                          C entailment model  a separate NLI classifier: does the section imply the sentence?
   ▼
Employee sees: verdict on the answer · how the answer is reached · what's missing · suggested answer
               (✓ re-checked / ? partly / ✕ not confirmed) · 👍👎 feedback. Everything is logged to logs/.
```

### Module guide
| File | Role | Key design decision |
|---|---|---|
| `modules/input_guard.py` | Input checks, layer 1 + 2 | Cheapest checks first, so bad input never costs an API call. Personal data is masked **before** any model sees it. If the classifier fails, the question is treated as in scope (safe, because the answer is still verified). |
| `modules/banking_assistant.py` | **Agent 1** | Ordinary RAG assistant on the cheap model: same repository, top-2 passages, no version filtering. Never told to make mistakes. |
| `modules/policy_validation.py` | Which version applies on which date | Pure date logic in code. Detects dates in the question ("March 2025", "15/03/2025", "last year"); future dates fall back to today. |
| `modules/claim_extractor.py` | Answer → claims | Self-contained claims, because each one is searched on its own. |
| `modules/evidence_retriever.py` | Semantic search | Searches the whole repository but filters each search to versions in effect. `search_many` uses claim + question; `expand_siblings` adds the other amount bands of the same rule. |
| `modules/claim_verifier.py` | 5-step derivation + verdict + root cause | The JSON schema puts `policy_requirement` **before** `status`, so the model works out the rule first and judges second. |
| `modules/policy_rules.py` | Deterministic checks | Numbers and units (incl. business days, months, times), required vs not required, quote exists, extraction guard. Rules never upgrade a verdict. |
| `modules/completeness.py` | Missing-step detection | At most 4 required elements, each must quote the policy word for word, or it's dropped. |
| `modules/correction.py` | Suggested answer | Only from passages in effect; one passage + quote per sentence, so each sentence can be re-checked alone. |
| `modules/reverify.py`, `modules/nli.py` | Re-check A + B + C | Different methods from the ones that wrote the correction. "Confirmed" only if every sentence passes all three. |
| `modules/event_log.py` | Logs | JSONL in `logs/`: verifications, failures, blocked inputs, feedback. |
| `modules/pipeline.py` | Orchestration + overall verdict | Most severe finding decides the headline. Same function used by the app, tests and evaluation. |
| `app.py` | Streamlit UI | Daily/audit modes, live stage progress, feedback, never a raw traceback. |

### Knowledge base (all synthetic)
| Document | Versions | What it tests |
|---|---|---|
| `SOP_OPS_021` Branch Cash Withdrawal SOP | v2.1 (superseded 30 Jun 2026), **v3.0** (from 1 Jul 2026) | Approval bands, dual approval, notice period, outdated versions |
| `SOP_OPS_034` Account Opening for Foreign Nationals | v1.4 | Multi-item document requirements (missing steps), applicability |
| `SOP_OPS_047` Customer Fee Waiver Authority | v2.0 | Authority limits by role, prohibitions |
| `TRAVEL_POLICY` Overseas Business Travel | v1.0 (superseded 31 Dec 2025), **v2.0** | Allowances, deadlines, dated questions ("in 2025") |
| `SOP_FIN_012` Staff Expense Claims SOP | v1.3 | Procedural steps |

Each document has metadata (`family`, `version`, `status`, `effective_date`, `expiry_date`, `applies_to`) in `policy_metadata.json`, and each current version has a hand-written **rules table** in `knowledge_base/rules/` (see the README there). A test fails if a rules table and its policy text drift apart.

---

## Evaluation
See **`eval/README.md`** for the full method, labelling guide and metric definitions. In short:
- **Live set** (`eval/questions.json`, 26 questions across 5 scenarios: correct, approval, outdated, missing step, missing evidence). Agent 1 answers live; a person labels the claims and answers; `compute_metrics.py` computes Macro F1, critical error recall, false positive rate, citation accuracy, incomplete-answer recall, correction support rate, verification time, and **System A (Agent 1 only) vs System B (Agent 1 + TrustGuard)**.
- **Ablation**: the same Agent 1 answers re-checked with TrustGuard on the cheap model (`--reuse ... --tg-model ...`).
- **Controlled set** (`eval/controlled_cases.json`, 12 fixed answers): regression check only, reported separately.

## Honest limitations (say these before the judges do)
- **SUPPORTED** means supported by the *available policy in effect*, not guaranteed true.
- Completeness lists at most 4 required elements, so long procedures can be partly checked.
- Method B only covers rule-type facts (amounts, periods, approvers, required/not required). Method C (NLI) is weak with exact numbers, which is why A and B check numbers.
- Applicability ("does this policy apply to this customer?") is judged by the LLM from each document's *applies to* line; only dates and versions are checked in code.
- Metrics come from our own small labelled set. Quote `metrics.md`, including the failures in `failures.md`.

## Configuration (`.env`)
| Variable | Default | Notes |
|---|---|---|
| `LLM_PROVIDER` | `gemini` | `gemini`, `claude`, or `mock` (offline heuristics for development only; the UI shows a warning) |
| `GEMINI_API_KEY` / `ANTHROPIC_API_KEY` | — | |
| `TRUSTGUARD_MODEL` | `gemini-3.5-flash-lite` / `claude-sonnet-5-5` | Newer/stronger. Paid key: `gemini-3.8-flash` (free tier allows only ~20 requests/day for Flash) |
| `AGENT1_MODEL` | `gemini-3.1-flash-lite` / `claude-haiku-5-5` | Older/cheaper |
| `AGENT1_KB_SCOPE` | `all` | `all` = whole repository incl. superseded versions (default), `approved` = current only, `none` |
| `AGENT1_TOP_K` | `2` | Passages Agent 1 reads |
| `ENABLE_NLI` / `NLI_MODEL` / `NLI_ENTAIL_THRESHOLD` | `true` / `cross-encoder/nli-deberta-v3-xsmall` / `0.5` | Re-check method C. Set `ENABLE_NLI=false` on low-memory hosting; A and B still run and the badge says "partly re-checked". |
| `GEMINI_MAX_OUTPUT_TOKENS` | `8192` | Room for the model's thinking + JSON |
| `LOG_DIR` | `logs` | |
| `GEMINI_MODEL` / `CLAUDE_MODEL` | — | **No longer used** (they set one model for both agents) |
