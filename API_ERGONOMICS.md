# DecisionLayer API: what was confusing, and what would help

Notes from building `decisionlayer-cli` against the public v1 API, the Swagger at `/api/v1/openapi.json`, and the two Python guides:

- https://www.decisionlayer.ai/api/create-a-consent-case
- https://www.decisionlayer.ai/api/create-a-case

The job asked for a working CLI **and** this write-up.

## Two products, not one “case”

The hire link is the **consent** guide. The full claimant/respondent loop the job describes lives on **contract-clause cases**.

| | Consent | Contract-clause |
| --- | --- | --- |
| Endpoint | `/api/v1/consent-cases` | `/api/v1/cases` |
| When | No DecisionLayer clause yet | Clause already in the contract |
| After POST | `ready_to_sign` → web sign/pay | `awaiting_signature` → web sign/pay/KYC |
| Respondent API | List only | Get, list, respond in turns |
| Extra fee | $20 consent letter + $500 filing | $500 filing |
| File field | `contract_files` (plural) | `contract_file` (singular) |

A new integrator following only the linked page cannot “respond to a case.” The consent resource never grows a response thread.

**Suggestion:** One overview page that says “pick A or B,” with a single state machine. Rename consent objects in the API (`consent_request_id` vs `case_id`) so they cannot be mixed up.

## Web steps are load-bearing, and invisible to a CLI

These are not API calls, on either path:

1. Sign arbitration terms
2. Pay the filing fee (and consent letter)
3. Verify identity
4. Respondent claims the case (Case ID + verification code)
5. View the award (`view_url` only)

The case object does help: `action_required`, `next_action`, `action_url`. The CLI can only print the URL and poll.

**What happened on a real filing (16 Sep 2026):** `POST /api/v1/cases` succeeded. The case landed in `awaiting_signature`. After the claimant signed on the web, the dashboard showed **Pending Payment** and **Pay Now**. The respondent account (a different login and API key, correct email on the case) still showed **zero cases**. DecisionLayer does not notify or list the respondent until the filing fee is paid. There is no API to pay, and no way to complete “both parties” from the CLI without a $500 web checkout. A sandbox key or `POST /api/v1/cases/{id}/pay-test` would make dual-party testing possible.

**Suggestions:**

- `POST /api/v1/cases/{id}/claim` with `{ "verification_code": "..." }` so a respondent agent can join without the dashboard.
- Hosted Checkout-style endpoints, or a signed short-lived `action_token` a CLI can open.
- Webhooks (`case.action_required`, `case.turn_changed`, `case.decided`) so clients do not poll.
- `GET /api/v1/cases/{id}/decision` returning the award metadata (even if the opinion stays on the web).

## Consent API is create/list only

Missing, and we had to paper over them in the CLI:

- `GET /api/v1/consent-cases/{id}`
- Pagination, `status` filter, `action_required` (all exist on `/cases`)
- Respondent accept / reject / sign
- Convert a `fully_executed` consent into a `/cases` object, or return the child `case_id`

`consent get` in the CLI lists everything and filters locally.

**Suggestion:** Same list/get/action envelope as `/cases`. Add `next_action` + `action_url` on consent objects. When consent is fully executed, include `arbitration_case_id`.

## Round fields are easy to get 422s from

`POST /api/v1/cases/{id}/responses` infers the round. Fields that do not apply are **rejected**, not ignored.

| Round | Who | Allowed extras |
| --- | --- | --- |
| 1 | Respondent | `evidence_response`, `evidence_demands`, `counterclaim_*` |
| 2 | Claimant | `evidence_response` |
| 3 | Respondent | argument + evidence only |

The OpenAPI schema lists every field as if they were always valid. The Python sample only sends `argument` + `evidence`.

This maps to the Rules (Claim → Answer → Reply → Response) but the API uses `round: 1..3` and `current_turn`. Small-claims cases under the Rules skip Reply/Response; the API still documents three rounds.

**Suggestions:**

- Return `next_round` and `accepted_fields[]` on `GET /cases/{id}`.
- 422 details should name the inferred round (they are already quite good otherwise).
- Publish a round table on the contract-case guide, not only in Swagger.

## Uploads: two protocols, easy to mix

Swagger: “Create **role-less** tickets.” 422 is also “a supplied **role**.” Sending `role` on `POST /api/v1/uploads` is therefore unsafe. This CLI omits `role` unless you pass `--role` on `upload sessions`.

Multipart files **or** `POST /api/v1/uploads` → PUT to GCS → `*_tickets`. Mixing them is 422. The consent guide never mentions tickets. Field names differ (`contract_file_ticket` vs `contract_files_tickets`).

Case/consent/response endpoints are declared `multipart/form-data`. A POST with only tickets and no files would otherwise be urlencoded; FastAPI often 422s that. The CLI always sends multipart.

**Suggestion:** One recommended path in the guides (multipart under 8 MiB, tickets above). Accept either per field without a 422 if the other is empty. Document PUT requirements (Content-Type, Content-Length). Drop or enumerate `role`.

## Error envelopes are not actually one shape

Guides show:

```json
{ "error": { "status": 422, "message": "...", "details": ["..."] } }
```

Swagger also documents FastAPI `HTTPValidationError` (`detail: [{ loc, msg, type }]`). Query-param 422s on `GET /cases` use that. The CLI accepts both.

**Suggestion:** Always return the `{ error: { status, message, details } }` envelope, including for query validation.

## List/get payload drift

- `GET /cases` example omits `current_turn`, `signed_at`, `paid_at`, `other_relief` that the schema allows.
- Consent list is an array with no pagination; case list is paged `limit`/`offset`.
- Consent statuses (`ready_to_sign`, `respondent_accepted`, …) are a different enum from case statuses.
- `GET /cases/{id}` OpenAPI lists 401/422 but the prose says 404.
- Filing 403 is in the contract guide, not in the consent guide, and not as a documented response on `POST /cases`.

**Suggestion:** One `Case` resource, discriminator `kind: consent | contract`. Shared pagination. Document every status code the server really sends.

## Auth and identity

- Keys are `Authorization: Bearer dvarb_...`, shown once at `/settings/api-keys`. Fine.
- Role is inferred from the key (`role: claimant | respondent`). Switching parties means switching keys. Correct, but the samples imply one script with `MY_ROLE`.
- `/api/me` exists (robots.txt) and is not in the public spec. A `GET /api/v1/me` would let the CLI print who a key is.
- Respondent 404 vs “not claimed yet” is indistinguishable.

**Suggestion:** Public `GET /api/v1/me`. 404 body: `"reason": "not_a_party" | "not_found" | "not_claimed"`.

## Docs vs Rules vs product copy

- Homepage: decision in ~45 days, $500–$2,500. Consent page: ~10 days in a simulated example. Rules: 14-day respondent ack, then 10/10/10 calendar days for Answer/Reply/Response.
- Homepage disclaimer: every award is finally reviewed by a human. Consent page: a pure-AI proceeding may issue an award without a human finally reviewing it; either party may request a human appeal.
- `Rule 20 Consent Awards` means a **settlement award**, not `POST /consent-cases`.
- Interactive playground on the guide is a **stateless demo**. The sample still shows `os.environ["DECISIONLAYER_API_KEY"]`. Easy to think Run hits production.

**Suggestion:** Label the playground `POST /api/v1/demo/consent-cases`. Align human-review language. Add a “Rules phase → API round” table.

## Endpoints that would make this CLI smaller

In priority order:

1. `POST /api/v1/cases/{id}/claim` `{ verification_code }`
2. Webhooks (or `GET /api/v1/events?since=`)
3. `GET /api/v1/me`
4. `GET /api/v1/cases/{id}/decision`
5. Consent get-by-id + accept/reject
6. `accepted_fields` / `next_round` on the case
7. `POST /api/v1/cases/{id}/sign` (even if it only returns a hosted signing URL with an expiry)
8. Idempotency keys on create/submit
9. `cursor` pagination instead of `offset`

## What already works well

- `action_required` + `next_action` + `action_url` is the right shape for a hybrid web/API product.
- 422 details are written for humans, not schema paths.
- Both parties share one response thread, oldest first.
- `dvarb_` prefix makes it obvious you pasted a session cookie by mistake.
- Filing lock behind approved accounts, with list/get/respond already live, is a reasonable rollout.
