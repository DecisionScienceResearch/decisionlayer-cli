# DecisionLayer CLI

Simple command-line client for the DecisionLayer public API. File a case as the **claimant**, respond as the **respondent**, and print the web steps the API cannot do (sign, pay, identity).

```bash
pip install -e .
python -m decisionlayer_cli --help
```

`decisionlayer` and `dl` are the same command. On Windows, if those names are not on PATH, keep using `python -m decisionlayer_cli`.

What was confusing, and what the API should add: [API_ERGONOMICS.md](API_ERGONOMICS.md).

## Install

Python 3.11+. Create keys at https://www.decisionlayer.ai/settings/api-keys (shown once, prefix `dvarb_`). You need **two accounts**: claimant and respondent.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e .

python -m decisionlayer_cli config set-key --profile claimant
python -m decisionlayer_cli config set-key --profile respondent
python -m decisionlayer_cli config show
```

Or copy `.env.example` to `.env` and set `DECISIONLAYER_API_KEY_CLAIMANT` / `DECISIONLAYER_API_KEY_RESPONDENT`.

Filing (`POST /api/v1/cases`) needs an approved account: casemanager@decisionlayer.ai. List, get, and respond work without that.

## Create a case (claimant)

This files a **contract-clause** case (`POST /api/v1/cases`). The job’s consent page (`POST /api/v1/consent-cases`) is a different resource — see below.

1. In `examples/sample_case.json`, set `respondent_email` to an inbox the respondent account can receive.

2. File:

```bash
python -m decisionlayer_cli --profile claimant case create \
  --from-json examples/sample_case.json \
  --contract examples/sample_contract.txt \
  --evidence examples/sample_evidence.txt
```

Or: `python -m decisionlayer_cli --profile claimant flow claimant --kind case`

3. Open the printed `action_url` while signed in as the claimant. Complete **on the web** (not API):

   1. `sign_terms`
   2. `pay_filing_fee`
   3. `verify_identity`

4. Track:

```bash
python -m decisionlayer_cli --profile claimant case watch CASE_ID --until awaiting_response
python -m decisionlayer_cli --profile claimant case get CASE_ID
python -m decisionlayer_cli --profile claimant case open CASE_ID
```

When `status` is `awaiting_response` and `current_turn` is `respondent`, the other party has been notified.

### Consent instead (no clause in the contract yet)

```bash
python -m decisionlayer_cli --profile claimant consent create \
  --question "Should the respondent return the $3,500 deposit?" \
  --demand 3500.00 \
  --other-relief "Return of any project files." \
  --respondent-first-name Jordan \
  --respondent-last-name Chen \
  --respondent-email respondent@example.com \
  --contract examples/sample_contract.txt
```

Lands in `ready_to_sign`. Sign and pay on `sign_url`. The respondent accepts or rejects **on the web**. There is no consent respond API.

## Respond to a case (respondent)

Use a **different** API key. The server only accepts `POST /api/v1/cases/{id}/responses` from `current_turn` while status is `awaiting_response` (otherwise 409). A respondent must sign terms on the web first.

1. Sign up with the email used as `respondent_email`. Claim the case (case ID + verification code) at https://www.decisionlayer.ai/respond.

2. Save that account’s key: `python -m decisionlayer_cli config set-key --profile respondent`

3. Inspect, then submit round 1 (Answer):

```bash
python -m decisionlayer_cli --profile respondent case get CASE_ID
python -m decisionlayer_cli --profile respondent response list CASE_ID

python -m decisionlayer_cli --profile respondent flow respondent CASE_ID \
  --from-json examples/sample_respondent_round1.json \
  --evidence examples/sample_reply_evidence.txt
```

Or:

```bash
python -m decisionlayer_cli --profile respondent response submit CASE_ID \
  --argument "Section 4.2 of the signed change order applied the deposit to discovery work." \
  --affirmation true \
  --evidence examples/sample_reply_evidence.txt \
  --evidence-response "The signed change order is attached." \
  --evidence-demands "The claimant's bank statement for March 2026."
```

4. After round 1 the case often asks the respondent to `verify_identity` on the web. Then the claimant files round 2 (Reply) with `--profile claimant`. Then the respondent files round 3. Wrong-round fields return 422. There is **no decision JSON** — open `view_url` when `status` is `decided`.

```bash
python -m decisionlayer_cli --profile claimant response submit CASE_ID \
  --argument "The change order was never signed by the claimant." \
  --evidence-response "No signed change order exists." \
  --affirmation true

python -m decisionlayer_cli --profile claimant case watch CASE_ID --until decided
python -m decisionlayer_cli --profile claimant case open CASE_ID --view
```

## Commands

| Command | API |
| --- | --- |
| `config set-key` / `show` | local keys |
| `consent create` / `list` / `get` | `POST/GET /api/v1/consent-cases` |
| `case create` / `list` / `get` / `inbox` / `watch` / `open` | `/api/v1/cases` |
| `response list` / `submit` | `/api/v1/cases/{id}/responses` |
| `upload sessions` / `cancel` | `/api/v1/uploads` (sessions also PUT the bytes) |
| `flow claimant` / `respondent` / `status` | guided dual-party walk |

`--json` prints raw API JSON. `--via-tickets` uses the two-step upload protocol (do not mix with multipart files on the same field). `--profile claimant|respondent` selects the key.

## Docs

- [API_ERGONOMICS.md](API_ERGONOMICS.md) — what was confusing, and API improvements
- [docs/CASE_FLOW.md](docs/CASE_FLOW.md) — status machines
- Official: [consent](https://www.decisionlayer.ai/api/create-a-consent-case) · [contract-clause](https://www.decisionlayer.ai/api/create-a-case) · [OpenAPI](https://www.decisionlayer.ai/api/v1/openapi.json)

Independent client. Not affiliated with Decision Science Research Corporation. Do not commit API keys.
