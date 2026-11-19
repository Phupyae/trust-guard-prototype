# Connecting an assistant to TrustGuard (API)

TrustGuard is a checking layer. Any AI assistant can use it: before showing an answer to staff, it sends
the question and the answer to TrustGuard and acts on the verdict. The assistant itself does not change.

```
Employee ─► Assistant (any) ──question + answer──► TrustGuard API /verify ──► verdict, problems, fix
                 ▲                                                   │
                 └──────────── show / hold / correct the answer ◄────┘
```

## Run it (prototype)
```powershell
uvicorn api:app --port 8000
```
- http://localhost:8000: test page that plays "another assistant" (HelpDesk Bot) calling the API
- http://localhost:8000/docs: interactive API documentation (try `/verify` from the browser)

The chat app (`streamlit run app.py`) and the API can run at the same time in two windows. Both use the
same checks and write to the same logs, so API checks also appear on the Improvements page.

## The call
`POST /verify`
```json
{
  "question": "A customer wants to withdraw $80,000 in cash today. Who needs to approve it?",
  "answer": "Withdrawals above $30,000 require Branch Manager approval.",
  "assistant": "Staff chatbot"
}
```
Reply (shortened):
```json
{
  "verdict": "do_not_use",
  "headline": "Don't use this answer",
  "safe_to_use": false,
  "needs_human_review": true,
  "statements": [{"statement": "...", "status": "does_not_match",
                  "sop": "Branch Over-the-Counter Cash Withdrawal SOP v3.0 §3.2",
                  "sop_says": "Withdrawals above $20,000 and up to $50,000 ...",
                  "likely_cause": "matches the superseded version 2.1 ..."}],
  "missing_steps": [],
  "suggested_answer": "Withdrawals above $20,000 and up to $50,000 require Branch Manager approval. ...",
  "suggested_answer_rechecked": "confirmed"
}
```
`verdict` is one of `matches_sop`, `use_with_care`, `incomplete`, `do_not_use`, `nothing_to_check`.
A calling assistant only needs one rule: **show the answer as checked only when `safe_to_use` is true**;
otherwise show the problems and the suggested answer, or send it for human review.

From Python:
```python
import requests
r = requests.post("http://localhost:8000/verify", json={"question": q, "answer": a}, timeout=90)
result = r.json()
```

## Security in the prototype
- Listens on localhost only. Set `TRUSTGUARD_API_KEY=...` in `.env` to require an `X-API-Key` header.
- Same input protection as the chat: length limits, prompt-injection check on the question and the answer,
  personal data masked before anything reaches the LLM or the logs, rate limit per caller.
- Errors return a plain message, never a stack trace.

## What production would add (future: integration with authorised OCBC systems)
The bank's API gateway and single sign-on in front of `/verify`, OCBC's governed SOP repository as the
policy source, and the review queue connected to the bank's case-management tool.
