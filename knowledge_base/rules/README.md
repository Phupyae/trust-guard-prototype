# Rules tables (re-check method B)

One JSON file per **approved** policy document, written by hand alongside the policy text.
It is the same policy written as data, the way a bank stores limits and approval rules in a
rules engine. It is **not** tied to any question or answer.

Used only when TrustGuard re-checks its own suggested correction (`modules/reverify.py`).
The comparison is plain Python, so no language model votes on whether the correction is right.

Per section:

| Field | Meaning | How it is checked |
|---|---|---|
| `quantities` | Every amount, limit or period the section states (`unit` + `value`) | Any quantity the sentence states in that unit must be one of these values |
| `roles` | Every approver or role the section names | Any role the sentence names must be one of these |
| `all_roles_required` | The section needs all of its roles together (e.g. dual approval) | If the sentence names one of them as an approver, it must name all of them |
| `required` | Steps that ARE required (`approval`, `receipts`, ...) | The sentence must not say they are not needed |
| `not_required` | Steps the section says are NOT required | The sentence must not say they are needed |
| `exemptions` | Items the section itself exempts from its `required` steps (e.g. TRAVEL_POLICY_V2 §5.2: `["daily allowance"]`, because "The daily allowance does not require receipts.") | A sentence that names an exempt item may say a `required` step is not needed for it. It still fails if it generalises with "any", "all" or "every" ("Receipts are not required for any expense, including the daily allowance"), and a sentence about any other item ("No receipts are needed for hotel expenses") still fails |

Optional fields (`all_roles_required`, `not_required`, `exemptions`) can be left out.

**Exemptions are also used when verifying the assistant's claims.** The claim-level
`policy_rules.requirement_check` (the code backstop on the LLM's verdict) reads the cited
section's `exemptions` from this table. It returns `n/a` only when the claim itself names an
exempt item ("The daily allowance does not require receipts."). Any other "not required" claim
is still a `mismatch` ("No receipts are needed for hotel expenses."), even though the section
contains an exemption sentence. Both places use the same matcher,
`policy_rules.names_exempt_item`, including the "any/all/every" guard.

Units: `money`, `percent`, `working days` (also matches "business days"), `days`, `nights`,
`hours`, `weeks`, `months`, `years`, `times`.

**Keep it in sync.** If you edit a policy in `knowledge_base/source/`, update its rules file too.
`pytest` checks that every number in each section appears in its rules entry and vice versa.
