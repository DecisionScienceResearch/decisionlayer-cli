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
    for name in ("case", "consent", "response", "flow", "config", "upload"):
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
        ],
    )
    assert result.exit_code != 0
    assert "contract" in result.output.lower()