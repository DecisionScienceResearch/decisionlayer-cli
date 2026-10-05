# DecisionLayer CLI (`dl`)

Built by [Archwares™](https://www.archwares.com).

A command-line client for the [DecisionLayer](https://www.decisionlayer.ai) public API. File an arbitration case as the **claimant** and respond as the **respondent**, each with their own API key.

- Python 3.11+
- Separate profiles for claimant and respondent keys, so you can play both sides on one machine
- Readable output with a “what to do next” hint, or `--json` for scripts
- Prints the web URL when the API cannot finish a step (sign, pay, identity)

What was confusing, and what the API should add: [API_ERGONOMICS.md](API_ERGONOMICS.md).

> **Before you start:** filing a real case needs an account DecisionLayer has approved for filing (email [casemanager@decisionlayer.ai](mailto:casemanager@decisionlayer.ai)). Signing terms, paying the **$500 filing fee**, verifying identity, and the respondent claiming the case only work on the website. The CLI prints `next_action` and opens that page for you.
>
> After the claimant signs, the case sits in **Pending Payment**. The respondent dashboard stays empty until the fee is paid. There is no pay API and no sandbox. List, get, and respond still work on cases you already belong to.

`decisionlayer` and `dl` are the same command. On Windows, if those names are not on PATH, use `python -m decisionlayer_cli` instead of `dl`.

## 1. Install

```bash
pipx install git+https://github.com/RafayKhattak/decisionlayer-cli.git
```

Or from a clone:

```bash
git clone https://github.com/RafayKhattak/decisionlayer-cli.git
cd decisionlayer-cli
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e .
```

Check it works:

```bash
dl --help
```

## 2. Save an API key for each party

Each party creates a key at https://www.decisionlayer.ai/settings/api-keys while signed in to **their own** account. The full key is only shown once (prefix `dvarb_`).

```bash
dl login --profile claimant      # paste the claimant's key when prompted
dl login --profile respondent    # paste the respondent's key when prompted
dl config show
```

`login` checks the key with `GET /api/v1/cases` first. Use `--skip-check` to save offline. Add `-p claimant` (or `--profile claimant`) to any later command to pick a profile.

You can also copy [`.env.example`](.env.example) to `.env` and set `DECISIONLAYER_API_KEY_CLAIMANT` / `DECISIONLAYER_API_KEY_RESPONDENT`.

## 3. Create a case (claimant)

This files a **contract-clause** case (`POST /api/v1/cases`). Consent-to-arbitrate is a different resource — see below.

### Option A: from a JSON file

Edit [`examples/sample_case.json`](examples/sample_case.json). Set `respondent_email` to an inbox the **respondent account** can receive. File paths are relative to the folder you run `dl` from.

```bash
dl -p claimant case create --from examples/sample_case.json \
  --contract examples/sample_contract.txt \
  --evidence examples/sample_evidence.txt
```

### Option B: with flags

```bash
dl -p claimant case create \
  --question "Should the respondent return the $3,500 project deposit?" \
  --argument "The contract required return of the deposit within 30 days. It has been 90 days." \
  --demand 3500.00 \
  --respondent-first-name Jordan --respondent-last-name Chen \
  --respondent-email jordan@example.com \
  --respondent-street "12 Main St" --respondent-city Austin --respondent-state TX --respondent-zip 78701 \
  --claimant-street "800 Oak Ave" --claimant-city Denver --claimant-state CO --claimant-zip 80202 \
  --contract examples/sample_contract.txt \
  --evidence examples/sample_evidence.txt
```

The output shows the new case ID (`case_…`), status, and the next web step:

```text
Status          awaiting_signature
Next action     sign_terms
Waiting on you  sign_terms
                https://www.decisionlayer.ai/cases/case_…/terms
```

Guided variant: `dl -p claimant flow claimant --kind case`

### Finish filing on the web

```bash
dl -p claimant case open CASE_ID     # sign the terms
dl -p claimant case get CASE_ID      # next_action becomes pay_filing_fee
dl -p claimant case open CASE_ID     # pay ($500; not an API call)
dl -p claimant case open CASE_ID     # verify identity
dl -p claimant case watch CASE_ID --until awaiting_response
```

Once those three web steps are done, status is `awaiting_response`, `current_turn` is `respondent`, and the respondent is notified. Until the fee is paid, `dl -p respondent case list` is empty.

## 4. Respond to a case (respondent)

Use the **respondent** key. The server only accepts `POST /api/v1/cases/{id}/responses` from `current_turn` while status is `awaiting_response` (otherwise 409).

1. Sign up with the email used as `respondent_email`. Claim the case (case ID + verification code) at https://www.decisionlayer.ai/respond and sign the terms. The API cannot do this. Until it is done, `next_action` is `sign_terms`.
2. Find the case and check that it is your turn:

   ```bash
   dl -p respondent case inbox
   dl -p respondent case get CASE_ID
   ```

3. Submit round 1 (Answer). This is the only round that accepts evidence demands and a counterclaim:

   ```bash
   dl -p respondent response submit CASE_ID \
     --argument "The deposit was forfeited under section 4.2 because work had begun." \
     --evidence examples/sample_reply_evidence.txt \
     --evidence-demands "The claimant's cancellation email." \
     --counterclaim-argument "Claimant owes for 5 hours of design work." \
     --counterclaim-amount 750.00 \
     --affirmation true
   ```

   Or from a file: `dl -p respondent flow respondent CASE_ID --from-json examples/sample_respondent_round1.json --evidence examples/sample_reply_evidence.txt`

4. After round 1 the case often asks the respondent to verify identity: `dl -p respondent case open CASE_ID`.

## 5. Take turns until the case is decided

Parties take turns (up to 3 rounds). The server infers the round. Fields that do not apply to the current round return **422**.

```bash
# claimant, round 2: reply and produce the evidence the respondent asked for
dl -p claimant response submit CASE_ID \
  --argument "No work had begun; see the cancellation email." \
  --evidence-response "Cancellation email attached." \
  --affirmation true

# either party: read the whole thread, oldest first
dl -p claimant response list CASE_ID

# wait until it's your turn again
dl -p respondent case watch CASE_ID --until-action
```

When status is `decided`, read the award with `dl case decision CASE_ID`. `view_url` is the same answer on the web. A 404 means it is not published yet.

## Consent cases (no pre-existing arbitration clause)

`POST /api/v1/consent-cases` is a different product. There is no response thread.

```bash
dl -p claimant consent create \
  --question "Should the respondent return the $3,500 deposit?" \
  --demand 3500.00 \
  --other-relief "Return of any project files." \
  --respondent-first-name Jordan \
  --respondent-last-name Chen \
  --respondent-email respondent@example.com \
  --contract examples/sample_contract.txt

dl -p claimant consent list
dl -p claimant consent get CONSENT_ID
```

A live key starts in `ready_to_sign`. The claimant signs with `dl consent sign`, then pays at `action_url` (filing fee plus a $20 consent letter). The respondent accepts or rejects with `dl consent accept` or `dl consent reject --yes`, then signs with `dl consent sign`.

A test key (`dvarb_test_...` from `/settings/test-api-keys`) records signature and payment as already complete, so create lands in `paid` and `action_url` is empty. `dl consent complete-respondent` then claims, accepts, and signs in one call. That command rejects a live key.

## Commands

| Command | What it does |
| --- | --- |
| `dl login -p NAME` | Save an API key under a profile (checks it first) |
| `dl whoami` | Account behind the active key (`GET /api/v1/me`) |
| `dl config show` | Masked keys, base URL, config path |
| `dl consent create \| list \| get ID` | Consent-to-arbitrate requests. `get` calls `GET /consent-cases/{id}` |
| `dl consent sign \| accept \| reject --yes \| claim \| complete-respondent` | Sign URL, respondent accept/reject, invitation-token claim, or the test-key one-shot |
| `dl case create` | File a contract-clause case (claimant) |
| `dl case list \| inbox` | Your cases; `inbox` is only those waiting on you. Pass `--cursor` for the next page |
| `dl case get ID` | Status, whose turn it is, `next_round`, `accepted_fields`, and what to do next |
| `dl case sign ID` | Signing URL for `sign_terms` |
| `dl case claim ID --code` | Respondent joins with the emailed verification code |
| `dl case decision ID` | Published award text and PDF URL |
| `dl case open ID [--view]` | Open the next web step (or the case page) |
| `dl case watch ID [--until S \| --until-action]` | Poll until status or `action_required` |
| `dl response submit ID --argument …` | Submit your round. Fields outside `accepted_fields` are refused locally |
| `dl response list ID` | The response thread, oldest first |
| `dl simulation create \| list \| get \| watch \| result` | One-shot simulation. Production key only. `list` recovers an id |
| `dl events` | Latest change per case or consent request, not a full history |
| `dl feedback "..."` | Send a note to the DecisionLayer team |
| `dl upload sessions FILES` | Two-step GCS tickets, then PUT the bytes. A supplied role is ignored |
| `dl flow claimant \| respondent \| status` | Guided dual-party walk |

Staging (test keys, simulations, and the routes above) is `https://staging.decisionlayer.ai`. Point the CLI at it with `--base-url` or `DECISIONLAYER_BASE_URL`. The default remains production. Test keys (`dvarb_test_...`, created at `/settings/test-api-keys`) are for contract and consent practice. Simulations reject them with 403. Use a production key from `/settings/api-keys` for `dl simulation`.

Official samples from the API guides, with keys read from the environment, are in [`examples/official/`](examples/official/).

`API_ERGONOMICS.md` is the 16 Sep production audit. [`API_ERGONOMICS_V2.md`](API_ERGONOMICS_V2.md) is the staging pass.

Global options: `-p`/`--profile`, `--api-key`, `--base-url`, `--json`. `--via-tickets` uses `POST /api/v1/uploads` instead of multipart files; do not mix both on the same field.

## Docs

- [API_ERGONOMICS.md](API_ERGONOMICS.md) — 16 Sep production audit
- [API_ERGONOMICS_V2.md](API_ERGONOMICS_V2.md) — 28 Sep staging audit
- [docs/CASE_FLOW.md](docs/CASE_FLOW.md) — status machines
- Official: [consent](https://www.decisionlayer.ai/api/create-a-consent-case) · [contract-clause](https://www.decisionlayer.ai/api/create-a-case) · [OpenAPI](https://www.decisionlayer.ai/api/v1/openapi.json)

## License

MIT. Copyright 2026 Archwares™. Independent client. Not affiliated with Decision Science Research Corporation. Do not commit API keys.
