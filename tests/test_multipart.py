from pathlib import Path

from decisionlayer_cli.client import _as_multipart, _build_multipart


def test_skips_empty_and_none():
    form, files = _build_multipart(
        {"question_for_arbitration": "Q", "other_relief": "", "title": None, "claimant_affirmation": True}
    )
    assert form["question_for_arbitration"] == "Q"
    assert "other_relief" not in form
    assert "title" not in form
    assert form["claimant_affirmation"] == "true"
    assert files == []


def test_repeatable_tickets():
    form, _files = _build_multipart(
        {"argument": "A"},
        ticket_groups={"evidence_tickets": ["t1", "t2"], "contract_file_ticket": ["only"]},
    )
    assert form["evidence_tickets"] == ["t1", "t2"]
    assert form["contract_file_ticket"] == "only"


def test_file_group(tmp_path: Path):
    path = tmp_path / "note.txt"
    path.write_text("hello", encoding="utf-8")
    form, files = _build_multipart({"argument": "A"}, file_groups={"evidence": [path]})
    assert form["argument"] == "A"
    assert files[0][0] == "evidence"
    assert files[0][1][0] == "note.txt"
    files[0][1][1].close()


def test_as_multipart_encodes_repeatable_tickets():
    parts = _as_multipart({"argument": "A", "evidence_tickets": ["t1", "t2"]}, [])
    names = [item[0] for item in parts]
    assert names == ["argument", "evidence_tickets", "evidence_tickets"]
    assert parts[0][1] == (None, "A")
    assert parts[1][1] == (None, "t1")
