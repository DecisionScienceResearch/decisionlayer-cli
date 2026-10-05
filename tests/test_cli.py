from typer.testing import CliRunner

from decisionlayer_cli.cli import app

runner = CliRunner()


def test_help():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "consent" in result.output
    assert "case" in result.output
    assert "response" in result.output
    assert "login" in result.output
    assert "simulation" in result.output
    assert "whoami" in result.output


def test_login_help():
    result = runner.invoke(app, ["login", "--help"])
    assert result.exit_code == 0
    assert "profile" in result.output.lower()
    assert "skip-check" in result.output


def test_case_create_help_accepts_from_alias():
    result = runner.invoke(app, ["case", "create", "--help"])
    assert result.exit_code == 0
    assert "--from" in result.output
    assert "--from-json" in result.output


def test_version():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "decisionlayer-cli" in result.output


def test_consent_help_lists_create_and_list():
    result = runner.invoke(app, ["consent", "--help"])
    assert result.exit_code == 0
    assert "create" in result.output
    assert "list" in result.output


def test_missing_key_exits_nonzero():
    result = runner.invoke(app, ["--api-key", "", "case", "list"], env={"DECISIONLAYER_API_KEY": ""})
    assert result.exit_code != 0


def test_subcommand_help():
    for name in ("case", "consent", "response", "flow", "config", "upload", "simulation"):
        result = runner.invoke(app, [name, "--help"])
        assert result.exit_code == 0, result.output


def test_case_create_requires_contract():
    result = runner.invoke(
        app,
        [
            "--api-key",
            "dvarb_test",
            "case",
            "create",
            "--question",
            "Q",
            "--argument",
            "A",
            "--respondent-first-name",
            "Jordan",
            "--respondent-email",
            "j@example.com",
            "--respondent-street",
            "12 Main St",
            "--respondent-city",
            "Austin",
            "--respondent-state",
            "TX",
            "--respondent-zip",
            "78701",
            "--claimant-street",
            "800 Oak Ave",
            "--claimant-city",
            "Denver",
            "--claimant-state",
            "CO",
            "--claimant-zip",
            "80202",
        ],
    )
    assert result.exit_code != 0
    assert "contract" in result.output.lower()


def test_consent_reject_requires_yes():
    result = runner.invoke(app, ["--api-key", "dvarb_test", "consent", "reject", "consent_1"])
    assert result.exit_code != 0
    assert "terminal" in result.output.lower()


def test_consent_last_name_depends_on_respondent_type():
    individual = runner.invoke(
        app,
        [
            "--api-key",
            "dvarb_test",
            "consent",
            "create",
            "--question",
            "Q",
            "--respondent-first-name",
            "Acme",
            "--respondent-email",
            "a@b.co",
        ],
    )
    assert individual.exit_code != 0
    assert "respondent_last_name" in individual.output

    from decisionlayer_cli.cli import _consent_required

    organization = _consent_required(
        {
            "question_for_arbitration": "Q",
            "respondent_first_name": "Acme",
            "respondent_email": "a@b.co",
            "respondent_type": "organization",
        }
    )
    assert "respondent_last_name" not in organization


def test_ensure_accepted_blocks_wrong_round_field():
    from decisionlayer_cli.cli import _ensure_accepted
    from decisionlayer_cli.errors import ConfigError

    try:
        _ensure_accepted(
            {"next_round": 3, "accepted_fields": ["argument", "affirmation", "evidence"]},
            ["argument", "affirmation", "counterclaim_argument"],
        )
    except ConfigError as exc:
        assert "counterclaim_argument" in str(exc)
    else:
        raise AssertionError("expected ConfigError")