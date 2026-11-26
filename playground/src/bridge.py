"""The whole Python side of the playground: call querygate and return JSON."""

import json

import querygate
from querygate.gate import RULE_DESCRIPTIONS, Policy, Refused, Rule, check


def about() -> str:
    return json.dumps(
        {
            "version": querygate.__version__,
            "rules": [{"id": rule.value, "refuses": RULE_DESCRIPTIONS[rule]} for rule in Rule],
        }
    )


def run(payload: str) -> str:
    request = json.loads(payload)
    try:
        policy = Policy.of(
            request["allow"],
            deny_columns=request["deny"],
            max_rows=request["max_rows"],
        )
    except ValueError as error:
        return json.dumps({"kind": "bad-policy", "message": str(error)})
    try:
        checked = check(request["sql"], policy)
    except Refused as refused:
        return json.dumps({"kind": "refused", "rule": refused.rule.value, "message": str(refused)})
    return json.dumps(
        {
            "kind": "allowed",
            "sql": checked.sql,
            "tables": list(checked.tables),
            "limit_added": checked.limit_added,
            "max_rows": checked.max_rows,
        }
    )
