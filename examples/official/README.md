# Official API samples

Archwares™ vendored the Python scripts from the DecisionLayer guides so they can be run from this repo.

The copies published on the site set `API_KEY = "PASTE_YOUR_KEY_HERE"` and `BASE_URL = "https://www.decisionlayer.ai"`, including on the staging guides. These copies read the environment instead:

```bash
set DECISIONLAYER_API_KEY=dvarb_...
set DECISIONLAYER_BASE_URL=https://staging.decisionlayer.ai
pip install requests
python examples/official/create_consent_case.py
python examples/official/create_real_case.py
python examples/official/run_simulation.py
```

`run_simulation.py` needs a production key. A test key (`dvarb_test_...`) is rejected with 403.

On staging, run `create_consent_case.py` and `create_real_case.py` with a test key. A production key files a real case. A test filing records signature, payment, and identity as already complete. `create_real_case.py` still prints that payment and identity follow the signature. That line is the guide's live-key path. On a test key, `next_action` is empty and the case is already `awaiting_response`. The script polls five times and then exits. It does not file the respondent's round. Respondents set `CASE_ID` and `VERIFICATION_CODE` in the environment.
