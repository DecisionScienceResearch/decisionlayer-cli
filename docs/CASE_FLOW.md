# Case flows

See also [API_ERGONOMICS.md](../API_ERGONOMICS.md).

## Contract-clause (`/api/v1/cases`)

```text
POST /cases
  → awaiting_signature     claimant web: sign_terms
  → awaiting_payment       claimant web: pay_filing_fee
  → awaiting_identity_verification  claimant web: KYC
  → respondent notified
  → awaiting_response, current_turn=respondent
       respondent web: claim + sign_terms
       POST /responses  round 1 Answer
       often verify_identity for respondent
  → awaiting_response, current_turn=claimant
       POST /responses  round 2 Reply
  → awaiting_response, current_turn=respondent
       POST /responses  round 3 Response
  → in_review / submitted / decided
       open view_url (no GET /decision)
```

Public statuses: `draft`, `awaiting_signature`, `awaiting_payment`, `awaiting_identity_verification`, `in_review`, `awaiting_response`, `submitted`, `decided`.

`next_action`: `complete_form` | `sign_terms` | `pay_filing_fee` | `verify_identity` | `respond`.

## Consent (`/api/v1/consent-cases`)

```text
POST /consent-cases  →  ready_to_sign
  web: sign + pay
  → paid / respondent_notified / respondent_viewing
  web: respondent accepts or rejects
  → respondent_rejected | fully_executed
```

API today: create + list only.

Auth: `Authorization: Bearer dvarb_...` from https://www.decisionlayer.ai/settings/api-keys
