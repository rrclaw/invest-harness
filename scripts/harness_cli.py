"""Unified CLI entry point for invest_harness workflows."""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from lib.alert import AlertManager
from lib.config import HarnessConfig
from lib.db import get_connection, init_db
from lib.hypothesis import HypothesisManager
from lib.notifications import NotificationService
from lib.review import ReviewGenerator
from lib.rules import RuleEngine
from lib.transport import build_transport_from_config
from scripts.cold_backup import run_backup
from scripts.ingest import run_ingest
from scripts.lock_hypothesis import check_and_lock
from scripts.post_verify import run_post_verify
from scripts.rule_audit import run_audit


@dataclass(frozen=True)
class HarnessPaths:
    root: Path
    config_dir: Path
    db_path: Path
    knowledge_dir: Path
    chroma_dir: Path
    dedup_file: Path
    hypotheses_dir: Path
    reviews_dir: Path
    rules_dir: Path
    backups_dir: Path


@dataclass
class HarnessContext:
    paths: HarnessPaths
    config: HarnessConfig
    conn: object
    notifier: NotificationService


def _project_root(project_root: str | Path | None = None) -> Path:
    if project_root is not None:
        return Path(project_root)
    return Path(__file__).resolve().parent.parent


def _paths(project_root: str | Path | None = None) -> HarnessPaths:
    root = _project_root(project_root)
    return HarnessPaths(
        root=root,
        config_dir=root / "config",
        db_path=root / "harness.db",
        knowledge_dir=root / "knowledge",
        chroma_dir=root / "chroma_storage",
        dedup_file=root / "knowledge" / "raw" / "seen_hashes.json",
        hypotheses_dir=root / "hypotheses",
        reviews_dir=root / "reviews",
        rules_dir=root / "rules",
        backups_dir=root / "backups",
    )


@contextmanager
def open_context(project_root: str | Path | None = None):
    paths = _paths(project_root)
    config = HarnessConfig(paths.config_dir)
    conn = get_connection(paths.db_path)
    init_db(conn)
    transport = build_transport_from_config(config, conn=conn)
    notifier = NotificationService(transport)
    try:
        yield HarnessContext(paths=paths, config=config, conn=conn, notifier=notifier)
    finally:
        conn.close()


def _read_json(path: str | Path) -> dict:
    with open(path) as f:
        return json.load(f)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def _default_verify_paths(reviews_dir: Path, date: str) -> list[Path]:
    day_dir = reviews_dir / date
    return sorted(day_dir.glob("post_market_*.json"))


def _load_verify_results(paths: list[Path]) -> list[dict]:
    return [json.loads(path.read_text()) for path in paths]


def _summarize_rule_audit(report: dict) -> str:
    return (
        f"Total active rules: {report['total_active']}\n"
        f"Semantic overlaps: {len(report['semantic_overlaps'])}\n"
        f"Dead rules: {len(report['dead_rules'])}\n"
        f"Bloat warning: {report['bloat_warning']}"
    )


def _summarize_backup(stats: dict) -> str:
    return (
        f"Datestamp: {stats['datestamp']}\n"
        f"DB backed up: {stats['db_backed_up']}\n"
        f"Chroma backed up: {stats['chroma_backed_up']}\n"
        f"Knowledge backed up: {stats['knowledge_backed_up']}\n"
        f"Raw backed up: {stats['raw_backed_up']}"
    )


def cmd_ingest(args, ctx: HarnessContext) -> dict:
    result = run_ingest(
        file_path=args.file,
        date=args.date,
        title=args.title,
        source_type=args.source_type,
        knowledge_dir=str(ctx.paths.knowledge_dir),
        chroma_dir=str(ctx.paths.chroma_dir),
        dedup_file=str(ctx.paths.dedup_file),
    )
    result["command"] = "ingest"
    return result


def cmd_hypothesis(args, ctx: HarnessContext) -> dict:
    hypothesis = _read_json(args.file)
    manager = HypothesisManager(ctx.paths.hypotheses_dir)
    manager.save_draft(hypothesis, args.date)

    result = {
        "command": "hypothesis",
        "saved": True,
        "market": hypothesis["market"],
        "date": args.date,
        "hypothesis_id": hypothesis["hypothesis_id"],
        "path": str(ctx.paths.hypotheses_dir / args.date / f"{hypothesis['market']}.json"),
    }
    if not args.no_notify:
        result["transport"] = ctx.notifier.send_approval_request(
            hypothesis,
            date=args.date,
            target=args.target,
        )
    return result


def cmd_lock(args, ctx: HarnessContext) -> dict:
    manager = HypothesisManager(ctx.paths.hypotheses_dir)
    if args.deadline_check:
        result = check_and_lock(manager, args.date, args.market)
        payload = {"command": "lock", "mode": "deadline_check", **result}
        if result["action"] == "unconfirmed":
            alert_mgr = AlertManager(ctx.conn)
            alert = alert_mgr.fire(
                "L2",
                args.market,
                (
                    f"Hypothesis {result['hypothesis_id']} was not approved "
                    f"before lock deadline on {args.date}"
                ),
                "lock_check",
                result["hypothesis_id"],
            )
            payload["alert"] = alert
            if not args.no_notify:
                payload["transport"] = ctx.notifier.send_alert(alert, target=args.target)
        return payload

    manager.lock(args.date, args.market, args.approved_by)
    locked = manager.load_for_date(args.date, args.market)
    return {
        "command": "lock",
        "mode": "approve",
        "date": args.date,
        "market": args.market,
        "approved_by": args.approved_by,
        "status": locked["status"],
    }


def cmd_verify(args, ctx: HarnessContext) -> dict:
    manager = HypothesisManager(ctx.paths.hypotheses_dir)
    hypothesis = (
        _read_json(args.hypothesis_file)
        if args.hypothesis_file
        else manager.load_for_date(args.date, args.market)
    )
    if hypothesis is None:
        raise FileNotFoundError(
            f"No hypothesis found for market={args.market!r} date={args.date!r}"
        )
    actuals = _read_json(args.actuals_file)
    result = run_post_verify(
        hypothesis=hypothesis,
        actuals=actuals,
        date=args.date,
        reviews_dir=str(ctx.paths.reviews_dir),
    )
    result["command"] = "verify"
    return result


def cmd_review(args, ctx: HarnessContext) -> dict:
    verify_paths = (
        [Path(path) for path in args.verify_file]
        if args.verify_file
        else _default_verify_paths(ctx.paths.reviews_dir, args.date)
    )
    verify_results = _load_verify_results(verify_paths)
    markdown = ReviewGenerator().generate_markdown(verify_results, args.date)

    output_path = ctx.paths.reviews_dir / args.date / "nightly_review.md"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown)

    result = {
        "command": "review",
        "date": args.date,
        "output_path": str(output_path),
        "verify_files": [str(path) for path in verify_paths],
    }
    if not args.no_notify:
        result["transport"] = ctx.notifier.send_review(
            review_date=args.date,
            markdown=markdown,
            market=args.market,
            target=args.target,
        )
    return result


def cmd_rule_update(args, ctx: HarnessContext) -> dict:
    engine = RuleEngine(args.rules_dir or ctx.paths.rules_dir)
    engine.update_status(
        rule_id=args.rule_id,
        new_status=args.status,
        source_file=args.source_file,
        deprecated_reason=args.deprecated_reason,
    )
    return {
        "command": "rule_update",
        "rule_id": args.rule_id,
        "status": args.status,
        "source_file": args.source_file,
    }


def cmd_rule_audit(args, ctx: HarnessContext) -> dict:
    report = run_audit(str(args.rules_dir or ctx.paths.rules_dir))
    output_path = ctx.paths.reviews_dir / args.date / "rule_audit.json"
    _write_json(output_path, report)

    result = {
        "command": "rule_audit",
        "date": args.date,
        "output_path": str(output_path),
        "report": report,
    }
    if not args.no_notify:
        result["transport"] = ctx.notifier.send_broadcast(
            title=f"Rule Audit {args.date}",
            body=_summarize_rule_audit(report),
            market="global",
            target=args.target,
            metadata={"output_path": str(output_path)},
        )
    return result


def cmd_backup(args, ctx: HarnessContext) -> dict:
    stats = run_backup(
        harness_dir=str(ctx.paths.root),
        date_override=args.date_override,
    )
    result = {
        "command": "backup",
        "stats": stats,
    }
    if not args.no_notify:
        result["transport"] = ctx.notifier.send_broadcast(
            title=f"Backup {stats['datestamp']}",
            body=_summarize_backup(stats),
            market="global",
            target=args.target,
            metadata={"backup_dir": str(ctx.paths.backups_dir)},
        )
    return result


COMMAND_HANDLERS = {
    "ingest": cmd_ingest,
    "hypothesis": cmd_hypothesis,
    "lock": cmd_lock,
    "verify": cmd_verify,
    "review": cmd_review,
    "rule_update": cmd_rule_update,
    "rule_audit": cmd_rule_audit,
    "backup": cmd_backup,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Unified invest_harness CLI")
    parser.add_argument(
        "--project-root",
        help="Harness project root directory",
        default=None,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("ingest", help="Ingest a file into knowledge")
    ingest.add_argument("--file", required=True)
    ingest.add_argument("--date", required=True)
    ingest.add_argument("--title", required=True)
    ingest.add_argument("--source-type", required=True)

    hypothesis = subparsers.add_parser(
        "hypothesis",
        help="Save a hypothesis draft and request approval",
    )
    hypothesis.add_argument("--file", required=True, help="Path to hypothesis JSON")
    hypothesis.add_argument("--date", required=True)
    hypothesis.add_argument("--target", help="Override transport target alias")
    hypothesis.add_argument(
        "--no-notify",
        action="store_true",
        help="Do not send approval request through transport",
    )

    lock = subparsers.add_parser("lock", help="Approve lock or run deadline lock check")
    lock.add_argument("--date", required=True)
    lock.add_argument("--market", required=True)
    lock.add_argument("--target", help="Override transport target alias")
    mode = lock.add_mutually_exclusive_group(required=True)
    mode.add_argument("--approved-by", help="Human approver for lock")
    mode.add_argument(
        "--deadline-check",
        action="store_true",
        help="Run timeout lock check and emit alert on unconfirmed draft",
    )
    lock.add_argument(
        "--no-notify",
        action="store_true",
        help="Do not send alert through transport during deadline check",
    )

    verify = subparsers.add_parser("verify", help="Run post-market verification")
    verify.add_argument("--date", required=True)
    verify.add_argument("--market", required=True)
    verify.add_argument("--actuals-file", required=True)
    verify.add_argument("--hypothesis-file")

    review = subparsers.add_parser("review", help="Generate nightly review")
    review.add_argument("--date", required=True)
    review.add_argument("--market", default="global")
    review.add_argument("--verify-file", action="append", default=[])
    review.add_argument("--target", help="Override transport target alias")
    review.add_argument(
        "--no-notify",
        action="store_true",
        help="Do not send nightly review through transport",
    )

    rule_update = subparsers.add_parser("rule_update", help="Update rule status")
    rule_update.add_argument("--rule-id", required=True)
    rule_update.add_argument("--status", required=True)
    rule_update.add_argument("--source-file", required=True)
    rule_update.add_argument("--rules-dir")
    rule_update.add_argument("--deprecated-reason")

    rule_audit = subparsers.add_parser("rule_audit", help="Run rule audit and broadcast summary")
    rule_audit.add_argument("--date", required=True)
    rule_audit.add_argument("--rules-dir")
    rule_audit.add_argument("--target", help="Override transport target alias")
    rule_audit.add_argument(
        "--no-notify",
        action="store_true",
        help="Do not send audit summary through transport",
    )

    backup = subparsers.add_parser("backup", help="Run backup and broadcast summary")
    backup.add_argument("--date-override")
    backup.add_argument("--target", help="Override transport target alias")
    backup.add_argument(
        "--no-notify",
        action="store_true",
        help="Do not send backup summary through transport",
    )

    return parser


def run_cli(argv: list[str] | None = None, *, project_root: str | Path | None = None) -> dict:
    parser = build_parser()
    args = parser.parse_args(argv)
    resolved_root = project_root if project_root is not None else args.project_root
    with open_context(resolved_root) as ctx:
        handler = COMMAND_HANDLERS[args.command]
        return handler(args, ctx)


def main(argv: list[str] | None = None) -> int:
    result = run_cli(argv)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
