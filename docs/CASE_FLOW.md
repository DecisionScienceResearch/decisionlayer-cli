# Case flows

Archwares™ notes for the DecisionLayer CLI. See also [API_ERGONOMICS.md](../API_ERGONOMICS.md) and [API_ERGONOMICS_V2.md](../API_ERGONOMICS_V2.md).

Staging origin: `https://staging.decisionlayer.ai`. Production origin: `https://www.decisionlayer.ai`.

Auth: `Authorization: Bearer dvarb_...` from `/settings/api-keys`. Test keys (`dvarb_test_...`) come from `/settings/test-api-keys`. `GET /api/v1/me` names the account. Role is per case, not per key.

## Contract-clause (`/api/v1/cases`)

```text
POST /cases
  → awaiting_signature
       POST /cases/{id}/sign   returns signing_url (does not complete the signature)
       web: pay_filing_fee, then verify_identity
  → respondent notified
  → awaiting_response, current_turn=respondent
       POST /cases/{id}/claim  {verification_code}   if GET reason is not_claimed
       POST /cases/{id}/sign
       POST /responses  round 1   only accepted_fields
       often verify_identity for the respondent
  → awaiting_response, current_turn=claimant
       POST /responses  round 2
  → awaiting_response, current_turn=respondent
       POST /responses  round 3
  → decided
       GET /cases/{id}/decision
```

Public statuses: `draft`, `awaiting_signature`, `awaiting_payment`, `awaiting_identity_verification`, `in_review`, `awaiting_response`, `submitted`, `decided`.

`next_action`: `complete_form` | `sign_terms` | `pay_filing_fee` | `verify_identity` | `respond`.

`next_round` is 1, 2, or 3 while a response is open. `accepted_fields` is the allow-list for that round. Case 404s set `error.reason` to `not_found`, `not_a_party`, or `not_claimed`.

`GET /events` keeps the latest change per case or consent request, not a history. `case.decided` means the decision endpoint will return the award. A decision 404 for an unpublished award sets `error.reason` to `not_published`. A rejected claim code is 403 with `invalid_code`.

A test key skips signing, payment, identity verification, claim codes, email, and the `in_review` pause between rounds. `test` is true on those objects.

`GET /simulations` lists simulation ids. They use the `case_` prefix and are not in `GET /cases`.

`POST /consent-cases/claim` binds a live consent request with the invitation token from the respondent email. A matching email alone does not make a key the respondent. `POST /feedback` sends a note to the DecisionLayer team.

Send `Idempotency-Key` on create and on submit. Page lists with `cursor` (`X-Next-Cursor`). Do not combine `cursor` with a non-zero `offset`.

Files under 8 MiB are multipart. At 8 MiB or larger, `POST /uploads`, PUT the bytes, then send the ticket field. Do not mix a file and a ticket on the same field. A `role` on the upload is ignored.

## Consent (`/api/v1/consent-cases`)

```text
POST /consent-cases  →  ready_to_sign
  POST /consent-cases/{id}/sign
  web: pay, unless the key is a test key (already paid, action_url null)
  → respondent
       POST /consent-cases/claim  {invitation_token}   live keys; email match is not enough
       POST .../accept or POST .../reject
       POST .../sign
       or, test key only: POST .../respondent   (claim + accept + sign, no email)
  → respondent_rejected | fully_executed
```

`fully_executed` is final. The id prefix is `creq_`. A consent request does not become a `/cases` object.

Statuses: `draft`, `awaiting_account`, `ready_to_sign`, `awaiting_signature`, `awaiting_payment`, `paid`, `respondent_notified`, `respondent_viewing`, `respondent_accepted`, `respondent_rejected`, `fully_executed`.

`next_action`: `sign_terms` | `pay_filing_fee` | `accept`. `accept` means accept or reject. `pay_filing_fee` is the website. `GET /consent-cases/{id}` reads one. List with `cursor`.

File fields are plural: `contract_files`, `contract_files_tickets`.

## Simulation (`/api/v1/simulations`)

Production keys only. Test keys receive 403.

```text
POST /simulations   one multipart body with both sides
  → processing | retrying
  → ready     GET /simulations/{id}/result
  → failed    message on the status object
```

`GET /simulations` lists ids for the production key, newest first. The id is prefixed `case_` and does not appear in `GET /cases`. Poll about every 10 seconds. `page_url` needs a signed-in browser. `pdf_url` is temporary. `text` remains.
