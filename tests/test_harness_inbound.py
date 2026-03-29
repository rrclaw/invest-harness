from pathlib import Path

from scripts.harness_inbound import parse_inbound_command, route_inbound_message
from tests.test_harness_cli import _bootstrap_project, _sample_hypothesis, _write_json


def test_parse_inbound_command_matches_harness_prefix():
    argv = parse_inbound_command('/harness backup --date-override 20260327')
    assert argv == ["backup", "--date-override", "20260327"]


def test_parse_inbound_command_ignores_non_harness_messages():
    assert parse_inbound_command("hello there") is None


def test_route_inbound_message_executes_cli(tmp_path):
    _bootstrap_project(tmp_path)
    hypothesis_path = tmp_path / "input_hypothesis.json"
    _write_json(hypothesis_path, _sample_hypothesis())

    result = route_inbound_message(
        f'/harness hypothesis --file "{hypothesis_path}" --date 2026-03-27 --no-notify',
        project_root=tmp_path,
        execute=True,
    )

    assert result["matched"] is True
    assert result["executed"] is True
    assert result["result"]["command"] == "hypothesis"
