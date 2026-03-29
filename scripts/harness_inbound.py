"""Inbound command routing hook for OpenClaw/Feishu -> Harness CLI."""

from __future__ import annotations

import argparse
import json
import shlex
from pathlib import Path

from scripts.harness_cli import run_cli


def extract_command_text(message_text: str) -> str | None:
    for marker in ("/harness ", "harness "):
        idx = message_text.find(marker)
        if idx >= 0:
            return message_text[idx:]
    stripped = message_text.strip()
    if stripped in {"/harness", "harness"}:
        return stripped
    return None


def parse_inbound_command(message_text: str) -> list[str] | None:
    command_text = extract_command_text(message_text)
    if command_text is None:
        return None

    tokens = shlex.split(command_text)
    if not tokens:
        return None

    prefix = tokens[0]
    if prefix not in {"/harness", "harness"}:
        return None
    return tokens[1:]


def route_inbound_message(
    message_text: str,
    *,
    project_root: str | Path | None = None,
    execute: bool = False,
) -> dict:
    argv = parse_inbound_command(message_text)
    if argv is None:
        return {
            "matched": False,
            "argv": [],
            "executed": False,
        }

    result = {
        "matched": True,
        "argv": argv,
        "executed": False,
    }
    if execute:
        # Suppress transport notifications: the calling agent (OpenClaw)
        # handles Feishu delivery from our stdout, so harness must not
        # double-deliver via its own transport.
        if "--no-notify" not in argv:
            argv = argv + ["--no-notify"]
        result["result"] = run_cli(argv, project_root=project_root)
        result["executed"] = True
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Route inbound OpenClaw/Feishu messages to Harness CLI")
    parser.add_argument("--message-text", required=True)
    parser.add_argument("--project-root")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute matched Harness CLI command instead of only parsing it",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = route_inbound_message(
        args.message_text,
        project_root=args.project_root,
        execute=args.execute,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
