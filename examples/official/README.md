# Guide samples

The Python samples from the DecisionLayer API guides. These copies read your key from the environment.

```bash
# macOS / Linux
export DECISIONLAYER_API_KEY=dvarb_...
export DECISIONLAYER_BASE_URL=https://staging.decisionlayer.ai
export RESPONDENT_EMAIL=REPLACE_WITH_THE_RESPONDENT_INBOX

# Windows PowerShell
# $env:DECISIONLAYER_API_KEY="dvarb_..."
# $env:DECISIONLAYER_BASE_URL="https://staging.decisionlayer.ai"
# $env:RESPONDENT_EMAIL="REPLACE_WITH_THE_RESPONDENT_INBOX"

pip install requests
python examples/official/create_consent_case.py
python examples/official/create_real_case.py
python examples/official/run_simulation.py
```

`RESPONDENT_EMAIL` is required for the consent and contract samples. Use an inbox that account can open. The scripts stop if that address is missing, starts with `REPLACE`, or ends in `@example.com`.

Use a test key (`dvarb_test_...`) and the staging host for a practice filing. Use a production key for `run_simulation.py`. A production key with `DECISIONLAYER_BASE_URL=https://www.decisionlayer.ai` files a real consent or contract case for `RESPONDENT_EMAIL`.

With a test key, `create_real_case.py` finishes with the case already in `awaiting_response`. With a production key, signing, payment, and identity continue on the website. The script files the claimant side and polls. To act as the respondent in that script, set `CASE_ID` and `VERIFICATION_CODE`.
