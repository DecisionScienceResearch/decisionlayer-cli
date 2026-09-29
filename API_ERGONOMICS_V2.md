# DecisionLayer API: staging review (28 Sep 2026)

Prepared by Archwares™.

This is the second pass. [API_ERGONOMICS.md](API_ERGONOMICS.md) is the 16 Sep production audit and stays as it was. The notes below start from the staging OpenAPI and the three guide pages on 28 Sep 2026. On 29 Sep 2026 the CLI and the three official samples were run against `https://staging.decisionlayer.ai`. Contract and consent calls used test keys. The simulation used a production key. No card was charged.

## Live test-key filings, 29 Sep 2026

Two fresh staging accounts, each with its own test key. Both returned `can_file_cases: true` from `GET /api/v1/me`. The respondent address on the filing was the respondent account's inbox. The settings page says a test key records signature, payment, and identity verification as already complete, and that the filing is not a real case.

### Contract case `case_01m3p1wcn9f6t9e4w36rcv3mng`

`POST /api/v1/cases` with the claimant test key, a text contract, and one evidence file returned 201 in a few seconds. The case object had `test: true`, `status: awaiting_response`, `current_turn: respondent`, `next_round: 1`, and the full round-1 `accepted_fields` list. `signed_at` and `paid_at` were set about one second after `created_at`. `action_required` was false and `action_url` was null for the claimant. The message was: "This is a test filing. Signature, payment, and identity verification were recorded as complete, and the case is ready for a response." The wrapper `action_url` was the case view URL, not a checkout page. No payment step appeared.

The respondent test key could `GET` the case immediately. `role` was already `respondent`. There was no `not_claimed` 404 and no `POST /claim`. `action_required` was true and `next_action` was `sign_terms`. `GET /cases` for that key listed the case. On 16 Sep, a live filing left the respondent list empty until the fee was paid. A test filing does not.

`POST /cases/{id}/sign` with the respondent test key returned 200, `provider: signwell`, and a signing URL that expired the next day. The case stayed on `sign_terms`. Opening that URL was not required. `POST /cases/{id}/responses` with argument, `affirmation=true`, and one text file returned 201 anyway. Round id `case_01m3p1wcn9f6t9e4w36rcv3mng:r1`, `submitted_by: respondent`, `due_at` fourteen days later (`2026-10-13T07:44:12`). The case then moved to `in_review` with `current_turn: null`, `next_round: null`, and `accepted_fields: []`. It did not open round 2. Both keys saw that status. `GET /cases/{id}/decision` returned 404, no `reason` field, message "No published decision is available for this case," and details that say to poll until `status` is `decided`.

So a test contract filing skips the claimant's sign, pay, and identity steps, lets the matching respondent account see the case without a verification code, still offers a SignWell URL, and accepts round 1 without that signature. It then goes to review instead of the documented three-round loop. That last part may be special to test filings. It should not be assumed for a live case.

### Consent request `creq_01m3p1zxyvepaa0je9whzgh7n1`
  
`POST /api/v1/consent-cases` with the claimant test key returned 201. The id prefix is `creq_`, not `case_`. Status was `paid`, not `ready_to_sign`. `signed_at` and `paid_at` were set within two seconds. `action_required` was false, `next_action` and `action_url` were null, and `sign_url` was still returned. Claimant name and email were filled from the account (`Archwares Claimant`). `confirmation_email_sent_at` stayed null. `contract_file_paths` came back as one string containing a JSON array, not as an array.

The respondent test key could `GET` it before any claim. `role` was `respondent`, `next_action` was `accept`, and `action_url` was a respondent review URL with its own token. The claimant `view_url` was `/consent/{id}/success` and did not include that token. `POST .../sign` as the claimant returned 409: "This consent case is not waiting on a signature from you." Details named `next_action` and said sign is only for `sign_terms`.

`POST /consent-cases/{id}/respondent` with the respondent test key returned 200 and status `fully_executed`. In the same second it set `respondent_claimed_at`, `respondent_accepted_at`, and `respondent_signed_at`, and set `respondent_user_id` to the respondent account. `confirmation_email_sent_at`, `respondent_first_viewed_at`, and `respondent_full_viewed_at` stayed null. Calling that endpoint again returned the same object, not 409. The object has no child `case_id` or `arbitration_case_id`.

### Events

`GET /api/v1/events?since=2026-09-29T07:40:00` after create returned one `case.updated` for the contract case. After the response and the consent completion, the same `since` returned the later `case.updated` and one `consent_case.updated`, and no longer returned the earlier case event. There was no `case.decided`. The feed behaved like the latest change per resource, not a log of every transition. Event ids look like `case:{id}:{timestamp}` and `consent_case:{id}:{timestamp}`.

### Official samples, same day

The scripts in `examples/official/` were run with `DECISIONLAYER_BASE_URL` set to staging. Contract and consent used the claimant test key, because those scripts call `DECISIONLAYER_API_KEY` and a production key would have filed a real case. The simulation script used the production key. All three exited 0.

`create_consent_case.py` created `creq_01m3p3qbn6e2xrcmcvfjf3bjmj` with status `paid` and printed the sign URL. The list call reported 2 consent cases on the first page, which matched the two test filings from this account. The script still addresses `jordan.chen@example.com`, the address baked into the guide, not the respondent test account.

`create_real_case.py` created `case_01m3p3qjxtf5d8ds10w0q3r0sj` with status `awaiting_response` and `current_turn` `respondent`. It printed `Next step: None` and the view URL, then the hardcoded line "Payment and identity verification follow there after you sign." That line is not true for this test filing. Five polls stayed on `awaiting_response` / respondent. The claimant had 0 cases waiting. The script does not submit the respondent's round, because it is holding the claimant key.

`run_simulation.py` queued `case_01m3p3sf15e39rg0jxtbcskhms`, polled `processing` four times, then `ready`, in under a minute. `GET .../result` returned award text and a PDF URL. The award ordered the respondent to pay the plaintiff $3,500.00. `GET /cases` with the same production key returned 2 contract cases and did not include that simulation id. The same create, sent with the claimant test key, returned 403: "Simulations require a production API key." Details: "Test API keys cannot run simulations."

The SignWell URL from the earlier respondent sign call was still not opened. The first contract case is still `in_review`, with no published award.

## What a caller should pick

| Goal | Start here | Key |
| --- | --- | --- |
| The contract already has a DecisionLayer clause | `POST /api/v1/cases` | Test key for practice, approved account for a real filing |
| Ask the other party to agree to arbitrate | `POST /api/v1/consent-cases` | Any key. `can_file_cases` is not required |
| See an award without a real case | `POST /api/v1/simulations` | Production key only. Test keys get 403 |

Guides: `/api/create-a-case`, `/api/create-a-consent-case`, `/api/run-a-simulation`.

## What got better since 16 Sep

The staging spec now has the routes the first report asked for:

- `GET /api/v1/me`
- `POST /api/v1/cases/{id}/claim` with `verification_code` (1–32 characters)
- `POST /api/v1/cases/{id}/sign` and `POST /api/v1/consent-cases/{id}/sign`, returning `signing_url`, `expires_at`, and `provider` (`signwell` or `hosted`)
- `GET /api/v1/cases/{id}/decision`
- `GET /api/v1/consent-cases/{id}`, plus accept, reject, and a test-only `POST .../respondent`
- `next_round` and `accepted_fields` on the case
- `Idempotency-Key` on case create, consent create, response submit, and simulation create
- `cursor` and `X-Next-Cursor` on case and consent lists. `offset` still works. A full offset page also returns a cursor
- `GET /api/v1/events?since=` with `case.updated`, `case.decided`, and `consent_case.updated`
- Case 404s document `error.reason`: `not_found`, `not_a_party`, `not_claimed`
- Upload `role` is ignored. The ticket’s later form field assigns the file
- Guides state the 8 MiB line: multipart below it, tickets at or above it
- Test keys, `test: true` on the object, and a consent path that is already paid

On a test key, the 29 Sep contract filing recorded signature, payment, and identity as complete and never showed a checkout. The contract guide still tells a caller to pay and verify identity at `action_url`. That sentence is true for a live key until a live filing shows otherwise. A test key is not that proof.

## Calls made

`GET /api/v1/me` and `GET /api/v1/cases?limit=0` with no key, 28 Sep 2026, both returned 401 and the documented envelope. `reason` was absent:

```json
{
  "error": {
    "status": 401,
    "message": "No API key was provided.",
    "details": [
      "Send your key in the Authorization header: 'Authorization: Bearer dvarb_your_key_here'.",
      "Create or manage keys at /settings/api-keys."
    ]
  }
}
```

`GET /api/v1/cases?limit=0` with `Authorization: Bearer dvarb_not_a_real_key` also returned 401, before query validation:

```json
{
  "error": {
    "status": 401,
    "message": "The provided API key is not valid.",
    "details": [
      "This key is not recognized or has been deleted.",
      "Generate a new key at /settings/api-keys and use its full value."
    ]
  }
}
```

So a bad query never reaches the 422 validator until the key is accepted. The old FastAPI `detail: [{loc, msg}]` shape was not reproduced on these two calls. Keep accepting both shapes until an authenticated 422 proves the old one is gone.

## What is still confusing

**Staging docs call production.** Every sample on the staging guides sets `BASE_URL = "https://www.decisionlayer.ai"`. Swagger examples for `action_url` and `view_url` use `https://www.decisionlayer.ai/cases/...`. Running a sample unchanged files against production. The copies in `examples/official/` read `DECISIONLAYER_BASE_URL` and default to staging.

**Required fields in the schema are not the required fields in the guide.** `POST /cases` marks four fields required. The guide’s 422 example also requires `contract_file` (pdf, docx, rtf, or txt) and `respondent_city`. Trust the guide until a live 422 says otherwise.

**403 is in the guide and missing from `POST /cases`.** The contract page still says an unapproved account gets 403 and should email casemanager@decisionlayer.ai. That status is not in the operation’s response list. Consent and simulation pages do not mention it. `GET /me` has `can_file_cases`, which is the right signal, and it is not mentioned on the contract guide.

**Idempotency 409 is documented in three different places.** The header text says a different body, or a retry while the lease is held (about a minute), is 409. Simulation’s 409 description says that. Case create, consent create, and response submit describe 409 as an incomplete upload, the wrong turn, or an unsigned respondent, and leave the idempotency conflict only on the header. Consent also says a failed upload releases the key, and a surviving draft replays a stored 500. That last sentence needs a live retry before anyone depends on it.

**`error.reason` disagrees with itself.** The schema says `reason` is set on arbitration-case 404s and omitted everywhere else. Simulation 404 prose says `reason not_found`. The example body shows `"reason": null`. Claim’s 404 prose is only “Case not found.”

**`accepted_fields` can be empty while the example omits `next_round`.** An `awaiting_signature` example has `accepted_fields: []` and does not show `current_turn`, `next_round`, `signed_at`, or `paid_at`. Clients should treat missing keys and explicit nulls as the same, and should read `accepted_fields` before posting a response. The response Try-it-out example only shows round 1.

**Lists and events page differently.** Case and consent cursors are the `X-Next-Cursor` header, absent on the last page. Events put `next_cursor` in the JSON body, null at the end. Do not send `cursor` with a non-zero `offset`. `action_required=false` is not defined. `GET /cases` excludes simulations.

**Simulations are easy to lose.** The id is prefixed `case_`, same as a real case, and there is no list or cancel. `page_url` needs the key owner to be signed in. `pdf_url` disappears when the public PDF window closes. `text` remains. Status `retrying` is normal. 429 means the monthly cap is used up. The request must be multipart even with no file. The sample sends an empty `contract_file` part because `requests` urlencodes when `files` is omitted.

**Signing is a URL, not a signature.** `POST .../sign` does not sign. Open `signing_url` before `expires_at` and call again after that. Pay and KYC are still `action_url`. After the respondent’s first response, the next wait is often identity verification.

**Consent test keys are a different product from live keys.** Create still returns `sign_url`. For a test key the spec says `action_url` is null because the filing is already paid. `POST .../respondent` claims, accepts, and signs without email, and live keys get 403. Until claim, the key’s email must match `respondent_email`. Reject is terminal and emails the claimant. There is still no `arbitration_case_id` when status is `fully_executed`.

**Small limits that the guides skip.** Upload `filename` is 1–1024 characters, `size` must be greater than 0, `content_type` is at most 255 characters. Cancel accepts 1–100 tickets. `claimant_affirmation` defaults to `""`, not `"true"`. Consent money on the read model must match a signed-decimal pattern. `respondent_type` and `filing_capacity` are plain strings, not enums.

**The playground is labeled, and the snippet next to it is not.** The Run button is described as a stateless demo that writes nothing. The Python beside it posts to production and sends a fresh `Idempotency-Key`, so it looks like the demo. Only consent and contract have a Run button. Simulation does not. Test keys are explained only on the simulation guide.

## What to change next

In the order a client actually hits them:

1. Make the staging guides and Swagger examples use `staging.decisionlayer.ai`, or print the origin the server is running on.
2. Put 403 on `POST /cases`, and point the contract guide at `can_file_cases`.
3. Use one 409 description for idempotency on every create and submit, and show what the stored-500 replay actually returns.
4. Make `error.reason` match the prose on simulation and claim 404s, or delete `reason` from those sentences.
5. Show round 2 and round 3 in the response examples, and include `next_round` in the case example.
6. Add `GET /api/v1/simulations` so a lost id is recoverable, and use a prefix other than `case_`.
7. Say what `action_required=false` does, or reject it.
8. Say on the contract guide what a test key skips. The 29 Sep filing recorded signature, payment, and identity as complete, showed no checkout, and put the respondent on the case without `POST /claim`. The respondent `next_action` was still `sign_terms`, a SignWell URL was returned, and round 1 was accepted without opening it. The case then went to `in_review` instead of round 2. Document whether that one-round path is only for test filings.
9. Return `arbitration_case_id` on a fully executed consent request if that handoff exists. The 29 Sep `fully_executed` object did not have one. Consent ids use the prefix `creq_`.
10. Make `GET /events` either a real history or say it keeps only the latest event per resource. A second poll with the same `since` dropped the earlier `case.updated`.
11. Return `contract_file_paths` as an array. It arrived as a string of JSON. `POST /cases` rejects a create that omits either party's street, city, state, or zip, even though those fields are not marked required. `POST /consent-cases` rejects a missing `respondent_last_name` the same way.
12. On an unpublished decision, the 404 details are already clear and `reason` was omitted. A missing simulation id did return `reason: not_found`. A missing consent id did not. A bad claim code is 403, "The verification code was not accepted," not a 404.

## What already works on the page

The index now offers consent, contract, and simulation as three choices. `accepted_fields` is the right way to stop round-field 422s. `action_required`, `next_action`, and `action_url` are still the right shape for the steps that stay on the web. The 401 body names the header and the settings page. Human-readable `details` are still the best part of the error design.
