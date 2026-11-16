"""``querygate``: check one query from the command line or from another program.

Exit status 0 means the query may run and the safe version is on standard output;
1 means it was refused and the reason is on standard error; 2 means bad arguments.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from querygate import __version__
from querygate.gate import Policy, Refused, check


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="querygate", description=__doc__.splitlines()[0])
    p.add_argument("sql", help="the query to check, or - to read it from standard input")
    p.add_argument(
        "--allow",
        action="append",
        required=True,
        metavar="PATTERN",
        help="table pattern the query may read, such as 'marts.*'; repeatable",
    )
    p.add_argument(
        "--deny-column",
        action="append",
        default=[],
        metavar="COLUMN",
        help="column that may never be read, bare or as table.column; repeatable",
    )
    p.add_argument("--max-rows", type=int, default=1000, help="row limit to enforce")
    p.add_argument("--dialect", default="duckdb", help="SQL dialect of the target database")
    p.add_argument("--json", action="store_true", help="print the verdict as one JSON object")
    p.add_argument("--version", action="version", version=f"querygate {__version__}")
    return p


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    sql = sys.stdin.read() if args.sql == "-" else args.sql
    try:
        policy = Policy.of(
            args.allow,
            deny_columns=args.deny_column,
            max_rows=args.max_rows,
            dialect=args.dialect,
        )
    except ValueError as err:
        print(f"querygate: {err}", file=sys.stderr)
        return 2
    try:
        checked = check(sql, policy)
    except Refused as err:
        if args.json:
            print(json.dumps({"allowed": False, "rule": err.rule.value, "reason": str(err)}))
        else:
            print(f"refused [{err.rule.value}]: {err}", file=sys.stderr)
        return 1
    if args.json:
        verdict = {
            "allowed": True,
            "sql": checked.sql,
            "tables": list(checked.tables),
            "limit_added": checked.limit_added,
        }
        print(json.dumps(verdict))
    else:
        print(checked.sql)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
