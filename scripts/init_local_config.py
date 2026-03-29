"""Initialize config/local from public examples.

This script writes local-only config files without embedding real secrets in the
repository. Existing files are preserved unless --force is provided.

The default initialization path is intentionally noop-first so a freshly cloned
public repository can run local smoke tests before any OpenClaw or Feishu
integration is enabled.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

EXAMPLE_ENV = ".env.example"
EXAMPLE_RUNTIME = "local.runtime.example.json"
EXAMPLE_WATCHLIST = "local.watchlist.example.json"
EXAMPLE_PORTFOLIO = "local.portfolio_snapshot.example.json"

TRANSPORT_TYPE_ALIASES = {
    "noop": "noop",
    "direct_feishu": "direct_feishu",
    "direct_feishu_api": "direct_feishu",
    "openclaw": "openclaw",
    "openclaw_feishu_plugin": "openclaw",
}


def _read_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _parse_pairs(values: list[str] | None) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for raw in values or []:
        key, sep, value = raw.partition("=")
        if not sep or not key:
            raise ValueError(f"Expected KEY=VALUE format, got: {raw!r}")
        parsed[key] = value
    return parsed


def _render_env(template_path: Path, overrides: dict[str, str]) -> str:
    lines: list[str] = []
    seen: set[str] = set()
    for line in template_path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            lines.append(line)
            continue
        key, _, value = line.partition("=")
        replacement = overrides.get(key, value)
        lines.append(f"{key}={replacement}")
        seen.add(key)

    for key, value in overrides.items():
        if key not in seen:
            lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def _normalize_transport_type(name: str | None) -> str | None:
    if name is None:
        return None
    try:
        return TRANSPORT_TYPE_ALIASES[name]
    except KeyError as e:
        raise ValueError(f"Unknown transport type: {name!r}") from e


def _resolve_config_root(
    *,
    project_root: str | Path | None = None,
    config_root: str | Path | None = None,
) -> Path:
    if project_root is not None and config_root is not None:
        raise ValueError("Specify either project_root or config_root, not both")
    if config_root is not None:
        return Path(config_root)
    if project_root is not None:
        return Path(project_root) / "config"
    return Path(__file__).resolve().parent.parent / "config"


def _write_text(path: Path, content: str, force: bool) -> str:
    if path.exists() and not force:
        return "skipped"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return "written"


def _write_json(path: Path, data: dict, force: bool) -> str:
    return _write_text(
        path,
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        force,
    )


def initialize_local_config(
    config_root: str | Path,
    *,
    provider: str | None = None,
    model: str | None = None,
    persona_name: str | None = None,
    persona_goal: str | None = None,
    bridge_sources: list[str] | None = None,
    historical_inputs: list[str] | None = None,
    enabled_markets: list[str] | None = None,
    adapters: dict[str, str] | None = None,
    rule_files: list[str] | None = None,
    feedback_system: str | None = None,
    review_timezone: str | None = None,
    retrospective_time: str | None = None,
    milestone_mode: str | None = None,
    transport_type: str | None = None,
    channel: str | None = None,
    openclaw_plugin_path: str | None = None,
    openclaw_workspace_root: str | None = None,
    feishu_groups: dict[str, str] | None = None,
    env_overrides: dict[str, str] | None = None,
    force: bool = False,
) -> dict[str, str]:
    root = Path(config_root)
    examples_dir = root / "examples"
    local_dir = root / "local"

    runtime = _read_json(examples_dir / EXAMPLE_RUNTIME)
    watchlist = _read_json(examples_dir / EXAMPLE_WATCHLIST)
    portfolio = _read_json(examples_dir / EXAMPLE_PORTFOLIO)

    if provider:
        runtime["llm"]["provider"] = provider
    if model:
        runtime["llm"]["model"] = model
    if persona_name:
        runtime["persona"]["name"] = persona_name
    if persona_goal:
        runtime["persona"]["goal"] = persona_goal
    if bridge_sources:
        runtime["knowledge"]["bridge_sources"] = bridge_sources
    if historical_inputs:
        runtime["knowledge"]["historical_inputs"] = historical_inputs
        runtime["knowledge"]["read_only_inputs"] = historical_inputs
    if enabled_markets:
        runtime["markets"]["enabled"] = enabled_markets
    if adapters:
        runtime["markets"]["adapters"].update(adapters)
    if rule_files:
        runtime["rules"]["default_rule_files"] = rule_files
    if feedback_system:
        runtime["feedback"]["feedback_system"] = feedback_system
    if review_timezone:
        runtime["feedback"]["review_timezone"] = review_timezone
    if retrospective_time:
        runtime["feedback"]["retrospective_time"] = retrospective_time
    if milestone_mode:
        runtime["feedback"]["milestone_mode"] = milestone_mode
    normalized_transport_type = _normalize_transport_type(transport_type)
    if normalized_transport_type:
        runtime["transport"]["type"] = normalized_transport_type
    if channel:
        runtime["transport"]["channel"] = channel
    elif normalized_transport_type == "noop":
        runtime["transport"]["channel"] = "none"
    elif normalized_transport_type in {"openclaw", "direct_feishu"}:
        runtime["transport"]["channel"] = "feishu"
    if openclaw_plugin_path:
        runtime["openclaw"]["plugin_path"] = openclaw_plugin_path
    if openclaw_workspace_root:
        runtime["openclaw"]["workspace_root"] = openclaw_workspace_root
    if feishu_groups:
        runtime["feishu"]["group_map"].update(feishu_groups)

    env_text = _render_env(examples_dir / EXAMPLE_ENV, env_overrides or {})
    if model:
        env_text = _render_env(
            examples_dir / EXAMPLE_ENV,
            {"LLM_MODEL": model, **(env_overrides or {})},
        )

    return {
        "runtime.json": _write_json(local_dir / "runtime.json", runtime, force),
        "watchlist.json": _write_json(local_dir / "watchlist.json", watchlist, force),
        "portfolio_snapshot.json": _write_json(
            local_dir / "portfolio_snapshot.json",
            portfolio,
            force,
        ),
        ".env": _write_text(local_dir / ".env", env_text, force),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize config/local templates (noop-first by default)"
    )
    parser.add_argument("--config-root", help="Config root path", default=None)
    parser.add_argument(
        "--project-root",
        help="Project root path; config is resolved from <project-root>/config",
        default=None,
    )
    parser.add_argument("--provider", help="Primary model provider")
    parser.add_argument("--model", help="Primary model id")
    parser.add_argument("--persona-name", help="Persona display name")
    parser.add_argument("--persona-goal", help="Persona goal")
    parser.add_argument(
        "--bridge-source",
        action="append",
        default=[],
        help="Bridge or upstream knowledge source path",
    )
    parser.add_argument(
        "--historical-input",
        action="append",
        default=[],
        help="Historical read-only knowledge input path",
    )
    parser.add_argument(
        "--market",
        action="append",
        default=[],
        help="Enabled market key (repeatable)",
    )
    parser.add_argument(
        "--adapter",
        action="append",
        default=[],
        help="Market adapter mapping, format MARKET=ADAPTER",
    )
    parser.add_argument(
        "--rule-file",
        action="append",
        default=[],
        help="Rule file path (repeatable)",
    )
    parser.add_argument("--feedback-system", help="Feedback system id")
    parser.add_argument("--review-timezone", help="Review timezone")
    parser.add_argument("--retrospective-time", help="Retrospective time")
    parser.add_argument("--milestone-mode", help="Milestone mode")
    parser.add_argument(
        "--transport-type",
        choices=sorted(TRANSPORT_TYPE_ALIASES),
        help="Channel transport type",
    )
    parser.add_argument("--channel", help="Logical channel id")
    parser.add_argument("--openclaw-plugin-path", help="OpenClaw plugin path")
    parser.add_argument("--openclaw-workspace-root", help="OpenClaw workspace root")
    parser.add_argument(
        "--feishu-group",
        action="append",
        default=[],
        help="Feishu group mapping, format ALIAS=CHAT_ID",
    )
    parser.add_argument(
        "--env",
        action="append",
        default=[],
        help="Local env override, format KEY=VALUE",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing files in config/local",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    try:
        config_root = _resolve_config_root(
            project_root=args.project_root,
            config_root=args.config_root,
        )
    except ValueError as e:
        parser.error(str(e))

    result = initialize_local_config(
        config_root,
        provider=args.provider,
        model=args.model,
        persona_name=args.persona_name,
        persona_goal=args.persona_goal,
        bridge_sources=args.bridge_source or None,
        historical_inputs=args.historical_input or None,
        enabled_markets=args.market or None,
        adapters=_parse_pairs(args.adapter),
        rule_files=args.rule_file or None,
        feedback_system=args.feedback_system,
        review_timezone=args.review_timezone,
        retrospective_time=args.retrospective_time,
        milestone_mode=args.milestone_mode,
        transport_type=args.transport_type,
        channel=args.channel,
        openclaw_plugin_path=args.openclaw_plugin_path,
        openclaw_workspace_root=args.openclaw_workspace_root,
        feishu_groups=_parse_pairs(args.feishu_group),
        env_overrides=_parse_pairs(args.env),
        force=args.force,
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
