#!/usr/bin/env python3
"""Render or check the IntendmentArbitrator transition tables from the YAML source.

  render.py table                     print the Markdown tables
  render.py check <spec.md>           exit 1 if the tables in <spec.md> differ from the source
  render.py fixtures                  print the transitions as JSON, for property-test harnesses
"""
import json
import os
import re
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "intendment-arbitrator-state-machine.yaml")
BEGIN, END = "<!-- generated:begin -->", "<!-- generated:end -->"


def load():
    with open(SOURCE, encoding="utf-8") as f:
        return yaml.safe_load(f)


def cell(items):
    return "; ".join(items) if items else "—"


def table(doc):
    out = ["| id | from | move | who | precondition | money | to | stage |", "|---|---|---|---|---|---|---|---|"]
    for t in doc["transitions"]:
        out.append(
            "| {id} | {frm} | `{move}` | {who} | {pre} | {money} | {to} | {stage} |".format(
                id=t["id"],
                frm=", ".join(f"`{s}`" for s in t["from"]) or "—",
                move=t["move"],
                who=t["who"],
                pre=cell(t["pre"]),
                money=cell(t["money"]),
                to=", ".join(f"`{s}`" for s in t["to"]),
                stage=t["stage"],
            )
        )
    out += ["", "| id | move | who | precondition | effect |", "|---|---|---|---|---|"]
    for g in doc["reserve_operations"]:
        out.append(
            "| {id} | `{move}` | {who} | {pre} | {effect} |".format(
                id=g["id"], move=g["move"], who=g["who"], pre=cell(g["pre"]), effect=cell(g["effect"])
            )
        )
    out += ["", "| id | invariant | statement |", "|---|---|---|"]
    for i in doc["invariants"]:
        out.append(f"| {i['id']} | {i['name']} | {i['text']} |")
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
    elif argv[1:2] == ["fixtures"]:
        print(json.dumps({"version": doc["version"], "states": doc["states"], "transitions": doc["transitions"],
                          "invariants": doc["invariants"]}, indent=2, ensure_ascii=False))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
