# TrustGuard Priority 2 — Checklist

## ✅ Built and tested offline (62 tests)
- [x] Same policy repository for both agents; unofficial FAQ removed
- [x] Two model tiers, same provider (TRUSTGUARD_MODEL strong, AGENT1_MODEL cheap) + same-model warning
- [x] Synthetic banking SOPs (cash withdrawal v2.1 → v3.0, foreign-national accounts, fee waivers) with SYNTHETIC banner and metadata
- [x] Policy validation: version in effect on today's date or the date in the question
- [x] 5-step "how we get the answer" derivation per claim + root cause (outdated version)
- [x] Completeness check (missing required steps)
- [x] Suggested correction + re-verification by A citation · B rules table · C entailment model
- [x] Typed questions with input checks (empty, long, gibberish, greeting, injection, personal data masking, rate limit, off-topic, unclear, action request, other languages)
- [x] Daily / audit mode toggle; employee feedback; JSONL logs
- [x] Evaluation: 26 live questions, labelling CSVs, metrics, System A vs B, ablation, controlled regression set

## ⏳ On your laptop (needs the API key)
- [ ] `pip install -r requirements.txt` → `pytest -q` → expect 62 passed
- [ ] Update `.env` from `.env.example`. Leave TRUSTGUARD_MODEL / AGENT1_MODEL empty for the free-tier pair. Remove the old GEMINI_MODEL line
- [ ] `streamlit run app.py`: sidebar → "TrustGuard" should show C entailment model: ready
- [ ] Try the 7 example questions + a few typed edge cases; screenshot good runs for the slides
- [ ] `python eval/run_eval.py --controlled` → check for ✗ (prompt issues show up here first)
- [ ] `python eval/run_eval.py --live --runs 1 --delay 6` (stop any time; continue with `--resume <folder>`) → label CSVs (split by scenario across the team) → `compute_metrics.py`
- [ ] Ablation: `--reuse <live folder> --tg-model gemini-3.5-flash-lite` → comparison table
- [ ] Put metrics.md tables + 2–3 failures from failures.md into the slides

## 🎤 Demo day
- [ ] Models cached before going on stage (start the app once on the venue Wi-Fi/hotspot)
- [ ] Backup video: $80,000 withdrawal (contradiction + outdated + missing step + correction), receipts (verified, daily mode), maternity leave (insufficient), one blocked input
