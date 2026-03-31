"""Unified CLI entry point for invest_harness workflows."""

from __future__ import annotations

import argparse
import json
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import hashlib
import logging
from datetime import datetime

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

logger = logging.getLogger(__name__)


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


def _default_llm_call(prompt: str, *, config=None) -> str:
    """Simple LLM call via OpenAI-compatible API using env vars."""
    import os
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package required for LLM calls. pip install openai")

    client = OpenAI(
        api_key=os.environ.get("LLM_API_KEY", ""),
        base_url=os.environ.get("LLM_BASE_URL"),
    )
    model = os.environ.get("LLM_MODEL", "deepseek-chat")
    resp = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
    )
    return resp.choices[0].message.content


def _candidate_to_hypothesis(candidate: dict, market: str, date: str) -> dict:
    """Convert ScanCandidate to hypothesis dict matching existing schema."""
    return {
        "market": market,
        "ticker": candidate["primary_ticker"],
        "direction": candidate["direction"],
        "thesis": candidate["thesis"],
        "entry_price": candidate.get("suggested_entry"),
        "target_price": candidate.get("suggested_exit"),
        "stop_loss": candidate.get("stop_loss"),
        "time_horizon": candidate.get("time_horizon", "1w"),
        "confidence": candidate["confidence"],
        "evidence_refs": [e["fact_id"] for e in candidate.get("evidence", [])],
        "risk_factors": candidate.get("risk_factors", []),
        "source": "scan_auto",
    }


def cmd_scan(args, ctx: HarnessContext) -> dict:
    from lib.run_store import RunStore
    from lib.scanner import Scanner, ScanConfig
    from lib.watchlist import list_tickers

    store = RunStore(ctx.conn)

    # Load watchlist
    wl_path = Path(args.watchlist) if args.watchlist else ctx.paths.config_dir / "local" / "watchlist.json"
    tickers_data = list_tickers(wl_path, market=args.market)
    tickers = [e["ticker"] for e in tickers_data] if isinstance(tickers_data, list) else []

    if not tickers:
        return {"status": "skipped", "reason": "empty_watchlist"}

    watchlist_hash = hashlib.sha256(json.dumps(sorted(tickers)).encode()).hexdigest()[:16]

    # Knowledge fingerprint
    knowledge_fingerprint = "static"
    try:
        normalized_dir = ctx.paths.knowledge_dir / "normalized"
        if normalized_dir.exists():
            mtimes = [f.stat().st_mtime for f in normalized_dir.rglob("*.jsonl")]
            if mtimes:
                knowledge_fingerprint = str(max(mtimes))
    except Exception:
        pass

    # Create run (idempotency check)
    run = store.create_run(
        phase="scan", market=args.market, trigger_source="cron",
        watchlist_hash=watchlist_hash, knowledge_fingerprint=knowledge_fingerprint,
        date=args.date,
    )
    if run["status"] == "skipped":
        return run

    store.update_status(run["run_id"], "running")

    try:
        from lib.knowledge import KnowledgePipeline
        from lib.chroma_client import ChromaManager

        chroma = ChromaManager(str(ctx.paths.chroma_dir))
        knowledge = KnowledgePipeline(
            ctx.paths.knowledge_dir, chroma,
            str(ctx.paths.knowledge_dir / "raw" / "seen_hashes.json"),
        )
        rules = RuleEngine(ctx.paths.rules_dir).load_for_market(args.market)

        scan_config = ScanConfig()
        runtime = ctx.config.runtime
        if "scan" in runtime:
            for k, v in runtime["scan"].items():
                if hasattr(scan_config, k):
                    setattr(scan_config, k, v)

        scanner = Scanner(
            knowledge=knowledge, chroma=chroma, run_store=store,
            llm_call=_default_llm_call, rules=rules, config=scan_config,
        )

        result = scanner.scan(market=args.market, date=args.date, watchlist_tickers=tickers)

        # Save candidates to run_store
        for c in result["candidates"]:
            store.save_candidate(
                run_id=run["run_id"], market=args.market,
                primary_ticker=c["primary_ticker"],
                related_tickers=c.get("related_tickers", []),
                direction=c["direction"], confidence=c["confidence"],
                thesis=c["thesis"], evidence=c.get("evidence", []),
                auto_action=c["auto_action"],
                suggested_entry=c.get("suggested_entry"),
                suggested_exit=c.get("suggested_exit"),
                stop_loss=c.get("stop_loss"),
                time_horizon=c.get("time_horizon"),
                risk_factors=c.get("risk_factors", []),
            )

        # Handle auto-lock hypotheses
        hyp_mgr = HypothesisManager(ctx.paths.hypotheses_dir)
        hypotheses = []
        for c in result["candidates"]:
            if c["auto_action"] in ("auto_lock", "await_approval"):
                hyp = _candidate_to_hypothesis(c, args.market, args.date)
                hyp_mgr.save_draft(hyp, args.date)
                if c["auto_action"] == "auto_lock":
                    hyp_mgr.lock(args.date, args.market, approved_by="system_auto_lock")
                hypotheses.append(hyp)

        # Save artifacts
        artifacts_dir = ctx.paths.root / "scans" / args.date / run["batch_id"]
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        (artifacts_dir / "candidates.json").write_text(
            json.dumps(result["candidates"], ensure_ascii=False, indent=2)
        )

        store.update_status(run["run_id"], "completed", artifacts={
            "candidates_path": str(artifacts_dir / "candidates.json"),
            "candidate_count": len(result["candidates"]),
        })

        return {
            "run_id": run["run_id"],
            "batch_id": run["batch_id"],
            "status": "completed",
            "summary": result["summary"],
            "candidates": result["candidates"],
            "hypotheses_created": len(hypotheses),
        }

    except Exception as e:
        logger.exception("Scan failed")
        store.update_status(run["run_id"], "failed", error=str(e))
        return {"run_id": run["run_id"], "status": "failed", "error": str(e)}


def cmd_feedback(args, ctx: HarnessContext) -> dict:
    proposal_id = args.approve_rule or args.reject_rule
    approved = args.approve_rule is not None

    date = args.date or datetime.now().strftime("%Y%m%d")
    proposals_path = ctx.paths.reviews_dir / date / "rule_proposals.json"
    if not proposals_path.exists():
        return {"status": "error", "error": f"No rule proposals found for {date}"}

    proposals = json.loads(proposals_path.read_text())
    target = None
    for p in proposals:
        if p.get("proposal_id") == proposal_id:
            target = p
            break

    if not target:
        return {"status": "error", "error": f"Proposal {proposal_id} not found"}

    from lib.feedback_engine import FeedbackEngine
    engine = FeedbackEngine(
        knowledge=None, chroma=None, llm_call=None,
        rules=RuleEngine(ctx.paths.rules_dir).load_active(),
    )
    result = engine.apply_rule_proposal(target, approved=approved, reason=args.reason)

    if approved and target.get("action") == "deprecate" and target.get("rule_id"):
        re = RuleEngine(ctx.paths.rules_dir)
        rules = re.load_all()
        for r in rules:
            if r.rule_id == target["rule_id"]:
                re.update_status(r.rule_id, "deprecated", r.source_file, target.get("rationale"))
                break

    # Update proposals file
    proposals_path.write_text(json.dumps(proposals, ensure_ascii=False, indent=2))

    return {"status": "completed", "proposal_id": proposal_id, "action": "approved" if approved else "rejected"}


def cmd_watchlist(args, ctx: HarnessContext) -> dict:
    from lib.watchlist import add_ticker, remove_ticker, list_tickers, detect_market

    wl_path = ctx.paths.config_dir / "local" / "watchlist.json"

    if args.watchlist_action == "add":
        market = args.market or detect_market(args.ticker)
        return add_ticker(wl_path, ticker=args.ticker, market=market, name=args.name)
    elif args.watchlist_action == "remove":
        market = args.market or detect_market(args.ticker)
        return remove_ticker(wl_path, ticker=args.ticker, market=market)
    elif args.watchlist_action == "list":
        result = list_tickers(wl_path, market=args.market)
        return {"watchlist": result}
    else:
        return {"error": "Unknown watchlist action. Use: add, remove, list"}


COMMAND_HANDLERS = {
    "ingest": cmd_ingest,
    "hypothesis": cmd_hypothesis,
    "lock": cmd_lock,
    "verify": cmd_verify,
    "review": cmd_review,
    "rule_update": cmd_rule_update,
    "rule_audit": cmd_rule_audit,
    "backup": cmd_backup,
    "scan": cmd_scan,
    "feedback": cmd_feedback,
    "watchlist": cmd_watchlist,
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

    # scan
    scan = subparsers.add_parser("scan", help="Scan knowledge base for investment opportunities")
    scan.add_argument("--market", required=True, choices=["a_stock", "hk_stock", "us_stock", "polymarket"])
    scan.add_argument("--date", required=True, help="Date YYYYMMDD")
    scan.add_argument("--watchlist", help="Override watchlist file path")
    scan.add_argument("--no-notify", action="store_true")

    # feedback
    feedback = subparsers.add_parser("feedback", help="Apply or reject rule proposals")
    fb_group = feedback.add_mutually_exclusive_group(required=True)
    fb_group.add_argument("--approve-rule", help="Approve a rule proposal by ID")
    fb_group.add_argument("--reject-rule", help="Reject a rule proposal by ID")
    feedback.add_argument("--reason", help="Rejection reason")
    feedback.add_argument("--date", help="Review date to find proposals")
    feedback.add_argument("--no-notify", action="store_true")

    # watchlist
    watchlist = subparsers.add_parser("watchlist", help="Manage watchlist tickers")
    wl_sub = watchlist.add_subparsers(dest="watchlist_action")
    wl_add = wl_sub.add_parser("add")
    wl_add.add_argument("--ticker", required=True)
    wl_add.add_argument("--market", help="Auto-detected if not provided")
    wl_add.add_argument("--name", help="Display name")
    wl_rem = wl_sub.add_parser("remove")
    wl_rem.add_argument("--ticker", required=True)
    wl_rem.add_argument("--market", help="Auto-detected if not provided")
    wl_list = wl_sub.add_parser("list")
    wl_list.add_argument("--market", help="Filter by market")
    watchlist.add_argument("--no-notify", action="store_true")

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
