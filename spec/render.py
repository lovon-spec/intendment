#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Render, validate or export the IntendmentArbitrator specification data.

  render.py table                     print the Markdown tables
  render.py check <spec.md>           exit 1 if the tables in <spec.md> differ from the source
  render.py validate                  exit 1 on duplicate ids, unknown states or events, bad stages
  render.py diagram                   print a Mermaid state diagram of the transitions
  render.py fixtures                  print states, transitions, reserve operations and invariants as JSON
"""
import json
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "intendment-arbitrator-state-machine.yaml")
BEGIN, END = "<!-- generated:begin -->", "<!-- generated:end -->"
STAGES = {"1a", "1b"}


def load():
    with open(SOURCE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cell(items):
    return "; ".join(items) if items else "—"


def table(doc):
    out = ["| id | from | move | who | precondition | money | to | events | stage |", "|---|---|---|---|---|---|---|---|---|"]
    for t in doc["transitions"]:
        out.append(
            "| {id} | {frm} | `{move}` | {who} | {pre} | {money} | {to} | {events} | {stage} |".format(
                id=t["id"],
                frm=", ".join(f"`{s}`" for s in t["from"]) or "—",
                move=t["move"],
                who=t["who"],
                pre=cell(t["pre"]),
                money=cell(t["money"]),
                to=", ".join(f"`{s}`" for s in t["to"]),
                events=", ".join(t["events"]) or "—",
                stage=t["stage"],
            )
        )
    out += ["", "| id | move | who | precondition | effect | events |", "|---|---|---|---|---|---|"]
    for g in doc["reserve_operations"]:
        out.append(
            "| {id} | `{move}` | {who} | {pre} | {effect} | {events} |".format(
                id=g["id"], move=g["move"], who=g["who"], pre=cell(g["pre"]), effect=cell(g["effect"]),
                events=", ".join(g["events"]) or "—",
            )
        )
    out += ["", "| id | invariant | statement |", "|---|---|---|"]
    for i in doc["invariants"]:
        out.append(f"| {i['id']} | {i['name']} | {i['text']} |")
    return "\n".join(out)


def validate(doc):
    problems = []
    states = {s["id"] for s in doc["states"]}
    events = set(doc["events"])
    seen = set()
    for t in doc["transitions"]:
        if t["id"] in seen:
            problems.append(f"{t['id']}: duplicate id")
        seen.add(t["id"])
        for s in t["from"] + t["to"]:
            if s not in states:
                problems.append(f"{t['id']}: unknown state {s}")
        if not t["to"]:
            problems.append(f"{t['id']}: no target state")
        if t["stage"] not in STAGES:
            problems.append(f"{t['id']}: stage {t['stage']} not in {sorted(STAGES)}")
        for e in t["events"]:
            if e.rstrip("?") not in events:
                problems.append(f"{t['id']}: unknown event {e}")
        for key in ("who", "pre", "money"):
            if key not in t:
                problems.append(f"{t['id']}: missing {key}")
    for g in doc["reserve_operations"]:
        if g["id"] in seen:
            problems.append(f"{g['id']}: duplicate id")
        seen.add(g["id"])
        for e in g["events"]:
            if e.rstrip("?") not in events:
                problems.append(f"{g['id']}: unknown event {e}")
    for i in doc["invariants"]:
        if i["id"] in seen:
            problems.append(f"{i['id']}: duplicate id")
        seen.add(i["id"])
    used = {e.rstrip("?") for t in doc["transitions"] + doc["reserve_operations"] for e in t["events"]}
    for e in sorted(events - used):
        problems.append(f"event {e} is declared but emitted by no transition")
    terminal = {s["id"] for s in doc["states"] if "terminal" in s["meaning"]}
    reachable = set()
    for t in doc["transitions"]:
        reachable.update(t["to"])
    for s in terminal:
        if s not in reachable:
            problems.append(f"terminal state {s} is unreachable")
    return problems


def diagram(doc):
    out = ["stateDiagram-v2"]
    for t in doc["transitions"]:
        label = f"{t['id']} {t['move'].split('(')[0]}"
        sources = t["from"] or ["[*]"]
        for src in sources:
            for dst in t["to"]:
                if src == dst and len(t["to"]) > 1 and len(sources) > 1:
                    continue
                out.append(f"    {src} --> {dst}: {label}")
    for s in doc["states"]:
        if "terminal" in s["meaning"]:
            out.append(f"    {s['id']} --> [*]")
    return "\n".join(out)


def check(path, doc):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    m = re.search(re.escape(BEGIN) + r"\n(.*?)\n" + re.escape(END), text, re.S)
    if not m:
        print(f"{path}: no {BEGIN} … {END} block", file=sys.stderr)
        return 1
    if m.group(1).strip() != table(doc).strip():
        print(f"{path}: generated block differs from {os.path.basename(SOURCE)}", file=sys.stderr)
        return 1
    print("ok")
    return 0


def main(argv):
    doc = load()
    if argv[1:2] == ["table"]:
        print(table(doc))
    elif argv[1:2] == ["check"] and len(argv) == 3:
        return check(argv[2], doc)
    elif argv[1:2] == ["validate"]:
        problems = validate(doc)
        for p in problems:
            print(p, file=sys.stderr)
        print("ok" if not problems else f"{len(problems)} problem(s)")
        return 1 if problems else 0
    elif argv[1:2] == ["diagram"]:
        print(diagram(doc))
    elif argv[1:2] == ["fixtures"]:
        print(json.dumps({k: doc[k] for k in ("version", "symbols", "events", "states", "transitions", "reserve_operations", "invariants")},
                         indent=2, ensure_ascii=False))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
