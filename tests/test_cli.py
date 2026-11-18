import io
import json

import pytest

from querygate.cli import main
from querygate.gate import Rule

ALLOW = ["--allow", "marts.*"]


def test_an_allowed_query_is_printed_with_its_limit(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["select id from marts.cases", *ALLOW, "--max-rows", "50"]) == 0
    assert capsys.readouterr().out == "SELECT id FROM marts.cases LIMIT 50\n"


def test_a_refused_query_exits_1_with_the_rule_on_stderr(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["delete from marts.cases", *ALLOW]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("refused [read-only]: ")


def test_json_output_is_one_object_either_way(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["select id from marts.cases", *ALLOW, "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == {
        "allowed": True,
        "sql": "SELECT id FROM marts.cases LIMIT 1000",
        "tables": ["marts.cases"],
        "limit_added": True,
    }
    assert main(["select email from marts.users", *ALLOW, "--deny-column", "email", "--json"]) == 1
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["allowed"] is False and verdict["rule"] == "column"


def test_the_query_can_come_from_standard_input(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("select 1 from marts.a"))
    assert main(["-", *ALLOW, "--dialect", "postgres"]) == 0
    assert "FROM marts.a" in capsys.readouterr().out


def test_a_bad_policy_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["select 1", *ALLOW, "--max-rows", "0"]) == 2
    assert "positive" in capsys.readouterr().err


def test_rules_lists_every_rule_without_a_query(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--rules"]) == 0
    captured = capsys.readouterr()
    assert captured.err == ""
    for rule in Rule:
        assert f"{rule.value:<16} " in captured.out


def test_a_query_without_allow_still_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["select 1"])
    assert exc.value.code == 2
    assert "--allow" in capsys.readouterr().err
