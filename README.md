# DecisionLayer CLI (`dl`)

File a case, answer one, or preview an award from the terminal.

This is the [DecisionLayer](https://www.decisionlayer.ai) public API as commands. `dl` and `decisionlayer` are the same program. Built by [Archwares™](https://www.archwares.com).

- **Preview an award** in one request, before anyone is served
- **Practice both sides** on one machine with test keys, and skip the filing fee
- **File a live case** when a contract already has an arbitration clause, and **answer** it with the other party's key
- **Invite someone to arbitrate** when the contract does not have that clause yet
- **See whose turn it is**, submit only the fields that round accepts, and open the website when a step belongs there
- **Script it** with `--json`

Python 3.11 or newer. DecisionLayer is not a law firm and does not offer legal advice.

| You want to | Use |
| --- | --- |
| Read a sample award | [Preview an award](#preview-an-award) |
| Rehearse a filing | [Practice both sides](#practice-both-sides) |
| Open a real case | [File a live contract case](#file-a-live-contract-case) |
| Ask someone to agree to arbitrate | [Consent](#consent-to-arbitrate) |
| Answer a case that names you | [Respond](#respond) |

## Install

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
dl --help
```

If `dl` is not on your PATH, run `python -m decisionlayer_cli` instead.

## Keys

Create the key while signed in to the account that should own it. The full key is shown once.

| Goal | Key | Host |
| --- | --- | --- |
| Practice a contract or consent filing | Test key, prefix `dvarb_test_`, from [staging test keys](https://staging.decisionlayer.ai/settings/test-api-keys) | `https://staging.decisionlayer.ai` |
| Preview an award | Production key, prefix `dvarb_`, from [API keys](https://www.decisionlayer.ai/settings/api-keys) | `https://staging.decisionlayer.ai` |
| File a live case | Production key | `https://www.decisionlayer.ai` |

A live filing uses an account DecisionLayer has approved to file. Write to [casemanager@decisionlayer.ai](mailto:casemanager@decisionlayer.ai) for that.

Save two profiles when you want to play claimant and respondent on one machine. This does not change the host. The sections below say when to use staging.

```bash
dl login --profile claimant
dl login --profile respondent
dl -p claimant whoami
```

`login` checks the key before saving it. Add `--skip-check` to save offline. Later commands take `-p claimant` or `-p respondent`.

You can also copy [`.env.example`](.env.example) to `.env` and set `DECISIONLAYER_API_KEY`, `DECISIONLAYER_API_KEY_CLAIMANT`, `DECISIONLAYER_API_KEY_RESPONDENT`, and `DECISIONLAYER_BASE_URL`. `.env` stays on your machine.

Use the host the key belongs to. A test key belongs on staging. A live filing belongs on production.

## Preview an award

A simulation runs both sides in one request and returns an award. It uses a **production** key on staging. It does not open a case, notify anyone, or charge the filing fee. The id starts with `case_` and is listed with `dl simulation list`, not `dl case list`.

```bash
dl --base-url https://staging.decisionlayer.ai simulation create \
  --question "Should the respondent return the $3,500 deposit?" \
  --plaintiff-name "Avery Quinn" \
  --respondent-name "Jordan Chen" \
  --plaintiff-argument "The contract required the deposit back within 30 days. Delivery slipped, and the deposit was kept." \
  --respondent-argument "Delivery was late because the scope changed. The deposit was earned." \
  --demand 3500.00 \
  --contract examples/sample_contract.txt

dl --base-url https://staging.decisionlayer.ai simulation watch SIM_ID
dl --base-url https://staging.decisionlayer.ai simulation result SIM_ID
dl --base-url https://staging.decisionlayer.ai simulation list
```

`watch` polls until the award is ready. `result` reads it again. Keep `--base-url https://staging.decisionlayer.ai` on `create`, `watch`, `list`, and `result`. Each production key has a monthly simulation allowance.

## Practice both sides

Test keys are for learning the flow. Signature, payment, and identity are already recorded, the other test key can see the case immediately, and nothing is charged. Save the test keys into the profiles, even if those profiles already hold production keys. Replace the respondent email with the inbox of the respondent test key before you run the command:

```bash
dl config set-base-url https://staging.decisionlayer.ai
dl login --profile claimant
dl login --profile respondent
dl -p claimant case create \
  --question "Should the respondent return the $3,500 project deposit?" \
  --argument "The contract required return of the deposit within 30 days. It has been 90 days." \
  --demand 3500.00 \
  --respondent-first-name Jordan --respondent-last-name Chen \
  --respondent-email REPLACE_WITH_THE_RESPONDENT_TEST_INBOX \
  --respondent-street "12 Main St" --respondent-city Austin --respondent-state TX --respondent-zip 78701 \
  --claimant-street "800 Oak Ave" --claimant-city Denver --claimant-state CO --claimant-zip 80202 \
  --contract examples/sample_contract.txt \
  --evidence examples/sample_evidence.txt
```

Then answer with the respondent profile, using the commands in [Respond](#respond) and [Rounds](#rounds). A practice filing runs three rounds and finishes at `submitted`.

Read an award from [Preview an award](#preview-an-award), or from a live case after it is decided.

## File a live contract case

Use this when the contract already agrees to arbitration. Use a production key on the production host. If you were practicing, point the CLI back at production and save the claimant production key before you file. The respondent profile still holds the test key until [Respond](#respond).

```bash
dl config set-base-url https://www.decisionlayer.ai
dl login --profile claimant
```

A street, city, state, and ZIP are required for both parties, plus the contract file.

Edit [`examples/sample_case.json`](examples/sample_case.json) so `respondent_email` is an inbox that person can open, then:

```bash
dl -p claimant case create --from examples/sample_case.json \
  --contract examples/sample_contract.txt \
  --evidence examples/sample_evidence.txt
```

The same filing as flags. Replace the respondent email before you run it. On a production key this creates a real case for that inbox.

```bash
dl -p claimant case create \
  --question "Should the respondent return the $3,500 project deposit?" \
  --argument "The contract required return of the deposit within 30 days. It has been 90 days." \
  --demand 3500.00 \
  --respondent-first-name Jordan --respondent-last-name Chen \
  --respondent-email REPLACE_WITH_THE_RESPONDENT_INBOX \
  --respondent-street "12 Main St" --respondent-city Austin --respondent-state TX --respondent-zip 78701 \
  --claimant-street "800 Oak Ave" --claimant-city Denver --claimant-state CO --claimant-zip 80202 \
  --contract examples/sample_contract.txt \
  --evidence examples/sample_evidence.txt
```

You get a `case_…` id. Status starts at `awaiting_signature`. Sign, pay the $500 filing fee, and verify identity on the website. `dl case open` opens whatever step is current, so finish that page before you run it again.

```bash
dl -p claimant case open CASE_ID
```

Sign the terms in the browser. Then see the next step and open it:

```bash
dl -p claimant case get CASE_ID
dl -p claimant case open CASE_ID
```

Pay the filing fee on that page. Then open the step after payment:

```bash
dl -p claimant case open CASE_ID
```

Verify identity on that page. When those three are done, wait until the respondent can answer:

```bash
dl -p claimant case watch CASE_ID --until awaiting_response
```

After the fee is paid, the respondent is notified and it is their turn. `dl -p claimant case get CASE_ID` shows status, `current_turn`, `next_action`, and the link.

`dl -p claimant flow claimant --kind case` files the sample JSON for you. Change the respondent email in that file first.

## Respond

Use the respondent's own key, on the same host the case was filed on.

On a **live** case, sign up with the email on the filing and create a production key there. Save that key before the commands below. Practice leaves a test key in the respondent profile, and these commands would use it.

```bash
dl login --profile respondent
dl -p respondent case claim CASE_ID --code VERIFICATION_CODE
dl -p respondent case sign CASE_ID
```

The verification code is in the notice.

On a **test** case, keep the respondent test key in that profile. Claim and sign are already recorded. Go straight to the case:

```bash
dl -p respondent case inbox
dl -p respondent case get CASE_ID
```

Round 1 is the answer. It is the round that can include evidence demands and a counterclaim.

```bash
dl -p respondent response submit CASE_ID \
  --argument "The deposit was forfeited under section 4.2 because work had begun." \
  --evidence examples/sample_reply_evidence.txt \
  --evidence-demands "The claimant's cancellation email." \
  --counterclaim-argument "Claimant owes for 5 hours of design work." \
  --counterclaim-amount 750.00
```

Or `dl -p respondent flow respondent CASE_ID --from-json examples/sample_respondent_round1.json --evidence examples/sample_reply_evidence.txt`.

If the next step is identity, `dl -p respondent case open CASE_ID` opens it.

## Rounds

The parties alternate, up to three rounds. The server chooses the round. The CLI sends a field only when that round accepts it. Stay on the host where that case was filed, with that case's keys: test keys on staging, production keys on production.

```bash
# claimant, round 2
dl -p claimant response submit CASE_ID \
  --argument "No work had begun; see the cancellation email." \
  --evidence-response "Cancellation email attached."

dl -p claimant response list CASE_ID
dl -p respondent case watch CASE_ID --until-action
```

When a live case is `decided`, read the award:

```bash
dl -p claimant case decision CASE_ID
```

`view_url` is that award on the web. A practice filing stays at `submitted`, so use a simulation or a decided live case for the award text.

## Consent to arbitrate

Use this when you need the other party to agree to arbitration. There is no response thread. The id starts with `creq_`. An individual needs a last name. For a company, pass `--respondent-type organization` and put the company name in `--respondent-first-name`. A finished consent request stays a consent request. It does not become a `dl case`.

### Practice

Use test keys on staging. Replace the respondent email with the inbox of the respondent test key before you run the command.

```bash
dl config set-base-url https://staging.decisionlayer.ai
dl login --profile claimant
dl login --profile respondent
dl -p claimant consent create \
  --question "Should the respondent return the $3,500 deposit?" \
  --demand 3500.00 \
  --other-relief "Return of any project files." \
  --respondent-first-name Jordan \
  --respondent-last-name Chen \
  --respondent-email REPLACE_WITH_THE_RESPONDENT_TEST_INBOX \
  --contract examples/sample_contract.txt

dl -p claimant consent list
dl -p claimant consent get CONSENT_ID
```

Create already includes signature and payment. The respondent account email has to be that same address:

```bash
dl -p respondent consent complete-respondent CONSENT_ID
```

### A live request

Point the CLI at production and save the claimant production key. Replace the respondent email before you run the command. This creates a real request for that inbox.

```bash
dl config set-base-url https://www.decisionlayer.ai
dl login --profile claimant
dl -p claimant consent create \
  --question "Should the respondent return the $3,500 deposit?" \
  --demand 3500.00 \
  --other-relief "Return of any project files." \
  --respondent-first-name Jordan \
  --respondent-last-name Chen \
  --respondent-email REPLACE_WITH_THE_RESPONDENT_INBOX \
  --contract examples/sample_contract.txt
```

The request starts in `ready_to_sign`. Sign, then pay on the Action URL from `consent get` (the filing fee plus the consent letter):

```bash
dl -p claimant consent sign CONSENT_ID --open
dl -p claimant consent get CONSENT_ID
```

The respondent signs up with the email on the request and creates a production key. Save that key before claiming. Practice leaves a test key in the respondent profile, and the commands below would use it. A matching email is not enough on its own. The token is the last segment of the invitation link.

```bash
dl login --profile respondent
dl -p respondent consent claim --token INVITATION_TOKEN
dl -p respondent consent accept CONSENT_ID
dl -p respondent consent sign CONSENT_ID
```

`dl -p respondent consent reject CONSENT_ID --yes` declines and closes the request.

## Commands

| Command | What you get |
| --- | --- |
| `dl login -p NAME` | Save a key under a profile |
| `dl whoami` | The account behind the active key |
| `dl config show` | Masked keys, base URL, and where they are stored |
| `dl config set-base-url URL` | Point the CLI at production or staging |
| `dl simulation create \| list \| get \| watch \| result` | Preview an award. Production key on staging |
| `dl case create` | File a contract-clause case |
| `dl case list \| inbox` | Your cases. `inbox` is the ones waiting on you. `--cursor` turns the page |
| `dl case get ID` | Status, whose turn, the next step, and the fields this round accepts |
| `dl case sign ID` | Signing link |
| `dl case claim ID --code` | Join a live case with the code from the notice |
| `dl case open ID` | Open the next website step. `--view` opens the case page |
| `dl case watch ID` | Wait until a status (`--until`) or until it is your turn (`--until-action`) |
| `dl case decision ID` | The published award |
| `dl response submit ID --argument …` | File your round |
| `dl response list ID` | The thread, oldest first |
| `dl consent create \| list \| get ID` | Consent requests |
| `dl consent sign \| accept \| reject --yes \| claim \| complete-respondent` | Sign, accept, decline, claim an invitation, or finish a test consent |
| `dl events` | The latest change on each case or consent request |
| `dl feedback "…"` | A note to the DecisionLayer team |
| `dl upload sessions FILES` | Tickets for large files |
| `dl flow claimant \| respondent \| status` | A guided walk through the sample |

Add `--json` on any command for raw JSON. `-p` picks a profile. `--api-key` and `--base-url` override the saved key and host for that one command.

## Larger files

Pass the file on the command that files it (`--contract`, `--evidence`, and the other file flags). Under 8 MB it rides along with the request. At 8 MB the CLI uploads it first. Add `--via-tickets` to upload a smaller file that way too. The cap is 100 MB per file.

```bash
dl -p claimant case create --via-tickets --contract contract.pdf …
```

`dl upload sessions contract.pdf` uploads a file and prints a ticket. Case and consent commands do not take that ticket back. Pass the file path on those commands instead, as shown above. `dl upload cancel TICKET` drops a ticket you did not use.

The same `--idempotency-key` with the same body returns the original object. A different body sent with that key is rejected. Omit the flag and the CLI uses a new key.

## More detail

- [docs/CASE_FLOW.md](docs/CASE_FLOW.md) — statuses, turns, and which call comes next
- [examples/official/](examples/official/) — the guide samples, reading the key from the environment
- Guides: [consent](https://www.decisionlayer.ai/api/create-a-consent-case) · [contract case](https://www.decisionlayer.ai/api/create-a-case) · [OpenAPI](https://www.decisionlayer.ai/api/v1/openapi.json)

## License

MIT. Copyright 2026 Archwares™. Independent client. Not affiliated with Decision Science Research Corporation. Do not commit API keys.
