"""Merge both cross-check runs into data/crosscheck.json (run from data/).

crosscheck.py stops when OnFinality's keyless endpoint rate-limits it (HTTP 429), and then never writes
crosscheck.json. Run this only in that case, after crosscheck2.py: it prepends the results crosscheck.py printed
to crosscheck.log to the ones crosscheck2.py wrote."""
import json, ast
first = [ast.literal_eval(l) for l in open("crosscheck.log") if l.startswith("{")]
for r in first: r["note"] = "first run (onfinality, 500-block pieces); OOv2 part of that run hit onfinality 429 and was redone on publicnode"
cur = json.load(open("crosscheck.json"))
json.dump(first + cur, open("crosscheck.json", "w"), indent=1)
print(len(first + cur), all(r.get("match") for r in first + cur))
