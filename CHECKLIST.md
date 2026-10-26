# TrustGuard Priority 1 — Checklist (25–28 Oct)

## ✅ Done (built and tested offline)
- [x] Repo structure, config, `.env.example`, `.gitignore` (API key never committed)
- [x] 3 synthetic policy PDFs + metadata (incl. a superseded v1 for realism)
- [x] Document loader: PyMuPDF, splits on bold numbered headings → citable sections
- [x] Claim extraction (Claude, forced JSON via tool use)
- [x] Evidence retrieval (Sentence Transformers + cosine similarity; TF-IDF fallback)
- [x] Hybrid verification (Claude judge + numeric / requirement / quote rules)
- [x] Streamlit dashboard with live pipeline stages, evidence cards, JSON export
- [x] 6 labelled test cases (A Supported, B Contradicted, C Insufficient, D partial, E outdated, F SOP)
- [x] Extraction guard: altered-number and dropped-fact checks
- [x] 15 offline unit tests passing

## ⏳ Sun 25 Oct (tonight) — get it running on your laptop
- [ ] Get a free Gemini key at aistudio.google.com (or a paid Anthropic key)
- [ ] Clone repo → `python -m venv .venv` → activate → `pip install -r requirements.txt`
- [ ] `cp .env.example .env`, paste key
- [ ] `pytest -q` → expect 15 passed
- [ ] `streamlit run app.py` → run example **B**; you should see 2 × CONTRADICTED citing §4.2 and §7.2
- [ ] `python tests/run_eval.py` → note the accuracy; screenshot any ✗ rows

## ⏳ Mon 26 Oct — tune and harden (stop adding features tonight)
- [ ] `python scripts/inspect_retrieval.py` → check covered claims score above the threshold and maternity leave scores below it; adjust `MIN_RELEVANCE["sentence-transformers"]` in `config.py` if needed
- [ ] Fix any ✗ in `run_eval.py`: usually a prompt tweak in `claim_verifier.py`, or try `CLAUDE_MODEL=claude-sonnet-5-5`
- [ ] Abby: review/extend policy wording (`knowledge_base/source/*.md` → `python scripts/build_pdfs.py`)
- [ ] Maria: review extraction & verification prompts; add 5–10 more cases to `tests/test_cases.json`
- [ ] Try 3 "judge-style" curveball inputs (gibberish, very long answer, answer with no facts) → no crashes
- [ ] Freeze the code by end of day

## ⏳ Tue 27 Oct — demo prep
- [ ] Record backup demo video (examples B, A, C in that order; ~90 s)
- [ ] Final `run_eval.py` result → one honest number for the slide
- [ ] Slide 6 screenshots: claim cards + "How this was checked"
- [ ] Each member rehearses explaining one module (see README module guide)
- [ ] Optional ONLY if all above done: Priority 2 #7 version check (metadata already in place)

## 🎤 Wed 28 Oct — on the day
- [ ] Laptop: app already running and embedding model cached before going on stage
- [ ] Hotspot ready in case venue Wi-Fi blocks the API; backup video on desktop
