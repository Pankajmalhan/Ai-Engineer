#!/usr/bin/env python3
"""Extract one week from the AI Engineer Roadmap artifact HTML.

Usage: extract_week.py <artifact.html> <week>      e.g. 13, 1b, w16
       extract_week.py <artifact.html> --list      list every week id/title

The artifact embeds its whole plan as `var PLAN = {...};`. Prints the matching
week (plus quarter/month context) as JSON on stdout.
"""
import json
import re
import sys


def load_plan(path):
    html = open(path, encoding="utf-8").read()
    m = re.search(r"var PLAN\s*=\s*", html)
    if not m:
        sys.exit("PLAN not found in artifact HTML — the page structure may have changed")
    plan, _ = json.JSONDecoder().raw_decode(html, m.end())
    return plan


def iter_weeks(plan):
    for q in plan["quarters"]:
        for mo in q["months"]:
            for w in mo["weeks"]:
                yield q, mo, w


def norm(s):
    s = s.strip().lower()
    s = re.sub(r"^(week|wk|w)\s*", "", s)
    m = re.fullmatch(r"0*(\d+)([a-z]?)", s)
    return f"{int(m.group(1)):02d}{m.group(2)}" if m else s


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    plan = load_plan(sys.argv[1])
    if sys.argv[2] == "--list":
        for q, mo, w in iter_weeks(plan):
            print(f"{w['n']:>4}  {q['code']}/{mo['name']}  {w['title']}")
        return
    want = norm(sys.argv[2])
    for q, mo, w in iter_weeks(plan):
        if norm(w["n"]) == want:
            json.dump(
                {
                    "quarter": {"code": q["code"], "name": q["name"], "weekrange": q["weekrange"]},
                    "month": {"name": mo["name"], "theme": mo["theme"], "blurb": mo["blurb"]},
                    "week": w,
                },
                sys.stdout, indent=2, ensure_ascii=False,
            )
            print()
            return
    ids = ", ".join(w["n"] for _, _, w in iter_weeks(plan))
    sys.exit(f"Week '{sys.argv[2]}' not found. Available: {ids}")


if __name__ == "__main__":
    main()
