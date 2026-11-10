#!/usr/bin/env python3
"""Append one event to the durable swarm event log (swarm/events.jsonl).

Every event records who produced it (actor_kind):
  ai_subagent   - a Claude subagent reporting its own activity
  coordinator   - the lead orchestrator session
  script_worker - an ordinary script/process (model run worker); NOT an AI agent
Nothing in this log is simulated: events are only written by the actor that did the work.

usage: emit.py --actor NAME --kind ai_subagent --role ROLE --status started|progress|done|failed|blocked|handoff
               [--item WORK_ITEM] [--family F] [--msg TEXT] [--data JSON]
"""
import argparse, fcntl, json, os, time

LOG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "swarm", "events.jsonl")


def emit(actor, kind, role, status, item="", family="", msg="", data=None, log=LOG):
    os.makedirs(os.path.dirname(log), exist_ok=True)
    ev = {"ts": round(time.time(), 3), "actor": actor, "actor_kind": kind, "role": role, "status": status,
          "item": item, "family": family, "msg": msg}
    if data: ev["data"] = data
    with open(log, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
        fcntl.flock(f, fcntl.LOCK_UN)
    return ev


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--actor", required=True)
    ap.add_argument("--kind", default="ai_subagent", choices=["ai_subagent", "coordinator", "script_worker"])
    ap.add_argument("--role", required=True)
    ap.add_argument("--status", required=True, choices=["queued", "started", "progress", "done", "failed", "blocked", "handoff", "retried"])
    ap.add_argument("--item", default=""); ap.add_argument("--family", default="")
    ap.add_argument("--msg", default=""); ap.add_argument("--data", default="")
    a = ap.parse_args()
    emit(a.actor, a.kind, a.role, a.status, a.item, a.family, a.msg, json.loads(a.data) if a.data else None)
    print("ok")
