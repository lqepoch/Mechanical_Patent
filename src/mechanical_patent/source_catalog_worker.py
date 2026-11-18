"""Opt-in, restartable Docker worker for approved public RSS/Atom source monitoring.

Run only on an approved outbound network. It never reads private project cases,
calls a language model, or upgrades an AI-generated hypothesis to verified.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import signal
import sys
from threading import Event

from .problem_sources import ProblemSourceRegistry


def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser(description="Public-only patent problem source monitoring worker")
    p.add_argument("--storage-root", type=Path, default=Path("/data"))
    p.add_argument("--interval-minutes", type=int, default=180)
    p.add_argument("--max-sources", type=int, default=4)
    p.add_argument("--allow-public-network", action="store_true",
                   help="Explicit operator authorization for approved public RSS sources only")
    p.add_argument("--once", action="store_true", help="Run one cycle and exit")
    args=p.parse_args(argv)
    if not args.allow_public_network:
        p.error("后台监测只在明确 --allow-public-network 时启动")
    if not 15 <= args.interval_minutes <= 1440 or not 1 <= args.max_sources <= 20:
        p.error("轮询间隔必须为15至1440分钟，每轮最多20个来源")
    stop=Event()
    def shutdown(_signal, _frame):
        stop.set()
    signal.signal(signal.SIGTERM,shutdown)
    signal.signal(signal.SIGINT,shutdown)
    registry=ProblemSourceRegistry(args.storage_root)
    while not stop.is_set():
        try:
            result=registry.cycle(allow_network=True,max_sources=args.max_sources)
            # Avoid leaking URLs, article bodies and unredacted external service errors to logs.
            message={"at":datetime.now(timezone.utc).isoformat(),"status":result["status"],
                     "fetched":result["fetched"],"added":result["added"],
                     "failed_sources":[x["source_id"] for x in result["errors"]]}
            print(json.dumps(message,ensure_ascii=False),flush=True)
        except Exception as exc:
            print(json.dumps({"at":datetime.now(timezone.utc).isoformat(),
                              "status":"worker_cycle_error",
                              "error_type":type(exc).__name__}),file=sys.stderr,flush=True)
        if args.once:
            break
        stop.wait(args.interval_minutes*60)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
