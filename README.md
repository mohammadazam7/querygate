# querygate

[![CI](https://github.com/mohammadazam7/querygate/actions/workflows/ci.yml/badge.svg)](https://github.com/mohammadazam7/querygate/actions/workflows/ci.yml)

A SQL firewall for AI agents. Before a model-written query reaches your database,
querygate parses it and refuses it unless it is a single read, on tables you allowed,
away from columns you denied, with a row limit.

```python
from querygate import Policy, Refused, check

policy = Policy.of(["marts.*"], deny_columns=["customers.email"], max_rows=500)

check("select region, count(*) from marts.cases group by 1", policy).sql
# 'SELECT region, COUNT(*) FROM marts.cases GROUP BY 1 LIMIT 500'

check("select * from marts.cases; drop table marts.cases", policy)
# Refused: expected exactly one statement, got 2

check("select email from marts.customers", policy)
# Refused: column email may not be read
```

## Why

Giving an agent a database connection means running SQL written by something that can
be wrong, and that can be steered by text it read in your data. Prompts asking it to
behave are not a control. A read-only database role is, and you should use one, but a
role cannot stop a `SELECT` that reads a table the agent has no business with, pulls ten
million rows, calls `pg_read_file`, or sleeps for an hour. querygate is the check in
front of the connection: small, deterministic, and tested query by query.

## What it refuses

| Rule | Refused | Example |
|---|---|---|
| `parse` | Text that is not valid SQL in the target dialect | `selec * from marts.a` |
| `single-statement` | More than one statement | `select 1 from marts.a; drop table marts.a` |
| `read-only` | Writes, DDL, settings, transactions and unknown commands, anywhere in the tree; `SELECT INTO`; `FOR UPDATE` | `with gone as (delete from marts.a returning *) select * from gone` |
| `function` | Functions that read files, call other servers, sleep or change state | `select pg_read_file('/etc/passwd') from marts.a` |
| `table` | Tables outside the allow list, including in joins, subqueries and CTEs | `select * from marts.a where id in (select id from raw.b)` |
| `qualify` | Tables without a schema, so the search path cannot decide what is read | `select * from cases` |
| `source` | Table functions and files used as tables | `select * from read_csv('/etc/passwd')` |
| `column` | Denied columns in any position, and `*` on a table that has one | `select id from marts.customers order by email` |
| `limit` | A `LIMIT` that is not a plain number | `select id from marts.a limit (select 10)` |

A query that passes comes back rewritten in the target dialect with a row limit: added
when missing, cut down when larger than the policy allows, and applied to the whole
result of a `UNION`.

Queries are parsed with [sqlglot](https://github.com/tobymao/sqlglot) in the dialect you
name (`duckdb`, `postgres`, `bigquery`, `snowflake`, `mysql`, `tsql` and others) and
judged on the syntax tree, so comments, casing and spacing do not change the verdict.
Every refusal carries a stable rule name and a message written to be handed back to the
model, which is usually enough for it to fix the query on the next try.

## Install

```bash
pip install git+https://github.com/mohammadazam7/querygate
```

Not on PyPI yet. Python 3.11 or newer; the only dependency is sqlglot.

## Command line

```bash
$ querygate "select name, email from marts.customers" --allow 'marts.*' --deny-column customers.email
refused [column]: column email may not be read

$ echo "select region, count(*) from marts.cases group by 1" | querygate - --allow 'marts.*' --dialect bigquery
SELECT region, count(*) FROM marts.cases GROUP BY 1 LIMIT 1000

$ querygate "select id from marts.cases" --allow 'marts.*' --json
{"allowed": true, "sql": "SELECT id FROM marts.cases LIMIT 1000", "tables": ["marts.cases"], "limit_added": true}
```

Exit status is 0 when the query may run, 1 when it was refused, 2 for bad arguments, so
it drops into a shell pipeline or a tool wrapper in any language.

## In an agent

```python
def run_sql(sql: str) -> str:
    """The tool the model calls."""
    try:
        safe = check(sql, policy)
    except Refused as refusal:
        return f"Query refused ({refusal.rule.value}): {refusal}. Fix it and try again."
    return format_rows(connection.execute(safe.sql).fetchall())
```

## What it is not

- **Not a replacement for database permissions.** Connect with a read-only role that can
  see only what the agent needs. querygate is the second lock, not the only one.
- **Not a cost limiter.** A row limit bounds what comes back, not what the database scans.
  Use statement timeouts and, on warehouses that bill by bytes, a scan cap.
- **Column rules go by name.** `deny_columns=["customers.email"]` refuses any column
  named `email` in a query that reads `customers`. That is stricter than resolving
  aliases, and it means a view that renames the column needs its own rule.
- **The function block list is a list.** It covers the functions known to read files,
  reach other servers or change state in the supported databases. A database extension
  can add more; pass through a read-only role as well.

If you find a query that gets through and should not, that is a security bug: see
[SECURITY.md](SECURITY.md).

## Roadmap

- [x] The gate, the policy, the command line and a refusal test corpus
- [ ] An MCP server, so any agent can be given `run_sql` behind a policy file
- [ ] Policy files (YAML) with per-role allow lists
- [ ] Function allow lists per dialect instead of one shared block list
- [ ] Row filters: a mandatory predicate per table, such as a tenant or region
- [ ] PyPI release

## Development

```bash
python -m venv .venv && source .venv/bin/activate
make install
make check
```

New rules come with tests that contain the exact query. See
[CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT
