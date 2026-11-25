"""The check a model-written query must pass before it runs.

The model is untrusted: it can be wrong, and it can be steered by text it read in the
data. So nothing here trusts the query's intent. The text is parsed with the target
database's own dialect and judged on its syntax tree, not with string matching, which a
comment or odd spacing would defeat.
"""

from __future__ import annotations

import fnmatch
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import Enum
from typing import cast

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError


class Rule(Enum):
    """Why a query was refused. Stable identifiers, safe to log and to test against."""

    PARSE = "parse"
    SINGLE_STATEMENT = "single-statement"
    READ_ONLY = "read-only"
    FUNCTION = "function"
    TABLE = "table"
    QUALIFY = "qualify"
    SOURCE = "source"
    COLUMN = "column"
    LIMIT = "limit"


RULE_DESCRIPTIONS: dict[Rule, str] = {
    Rule.PARSE: "text that is not valid SQL in the target dialect",
    Rule.SINGLE_STATEMENT: "more than one statement",
    Rule.READ_ONLY: "writes, DDL, settings and unknown commands",
    Rule.FUNCTION: "functions that read files, call other servers, sleep or change state",
    Rule.TABLE: "tables outside the allow list",
    Rule.QUALIFY: "tables without a schema",
    Rule.SOURCE: "table functions and files used as tables",
    Rule.COLUMN: "denied columns in any position, and * on a table that has one",
    Rule.LIMIT: "a LIMIT that is not a plain number",
}


class Refused(ValueError):
    """The query may not run. ``rule`` says which check failed; the message says why
    in words that can be handed back to the model so it can fix the query."""

    def __init__(self, rule: Rule, message: str) -> None:
        super().__init__(message)
        self.rule = rule


# Statement roots that only read.
_READ_ROOTS = (exp.Select, exp.SetOperation)
# Anything that writes, changes settings or reaches outside the database, wherever it
# appears in the tree. ``Command`` is what the parser returns for statements it does not
# model (VACUUM, GRANT, CALL ...), so the unknown is refused too.
_WRITE_NODES = (
    exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Create, exp.Drop, exp.Alter,
    exp.TruncateTable, exp.Copy, exp.Command, exp.Pragma, exp.Set, exp.Use, exp.Attach,
    exp.Detach, exp.Transaction, exp.Commit, exp.Rollback, exp.Grant,
)  # fmt: skip
# Functions that read files, call other servers, sleep or change state from inside a
# SELECT. Matched by name in every dialect: refusing a harmless namesake is cheaper than
# missing one.
BLOCKED_FUNCTIONS = frozenset(
    {
        # DuckDB
        "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto",
        "read_text", "read_blob", "glob", "sniff_csv", "sqlite_scan", "postgres_scan",
        "mysql_scan", "query", "query_table", "getenv",
        # PostgreSQL
        "pg_read_file", "pg_read_binary_file", "pg_ls_dir", "pg_stat_file", "lo_import",
        "lo_export", "dblink", "dblink_exec", "pg_sleep", "pg_terminate_backend",
        "pg_cancel_backend", "set_config", "current_setting", "nextval", "setval",
        "pg_advisory_lock", "query_to_xml",
        # MySQL
        "load_file", "sleep", "benchmark", "get_lock",
        # SQL Server
        "openrowset", "opendatasource", "openquery", "xp_cmdshell",
        # BigQuery, Snowflake
        "external_query", "system$wait",
        # SQLite (fileio and extension loading)
        "readfile", "writefile", "edit", "fsdir", "load_extension",
        # Oracle (object types that open network connections)
        "httpuritype", "dburitype", "xdburitype",
    }
)  # fmt: skip
# Package-qualified calls such as Oracle's utl_http.request(...) are refused by package:
# these packages read files, open sockets, send mail, run jobs or call Java.
BLOCKED_PACKAGE_PREFIXES = ("utl_", "dbms_", "owa_", "sys.utl_", "sys.dbms_")


@dataclass(frozen=True)
class Policy:
    """What a query is allowed to touch.

    ``allow`` holds table patterns such as ``"marts.*"`` or ``"public.orders"``; a table
    must match one of them. ``deny_columns`` holds column names that may never be read,
    either bare (``"ssn"``, any table) or qualified by table (``"customers.email"``).
    """

    allow: frozenset[str]
    deny_columns: frozenset[str] = field(default_factory=frozenset)
    max_rows: int = 1000
    dialect: str = "duckdb"

    def __post_init__(self) -> None:
        if not self.allow:
            raise ValueError("a policy must allow at least one table pattern")
        if self.max_rows <= 0:
            raise ValueError("max_rows must be positive")

    @classmethod
    def of(
        cls,
        allow: Iterable[str],
        *,
        deny_columns: Iterable[str] = (),
        max_rows: int = 1000,
        dialect: str = "duckdb",
    ) -> Policy:
        return cls(
            frozenset(a.lower() for a in allow),
            frozenset(c.lower() for c in deny_columns),
            max_rows,
            dialect,
        )

    def allows(self, table: str) -> bool:
        """Whether a dotted table name matches a pattern, part by part.

        ``*`` never crosses a dot, so ``marts.*`` allows ``marts.cases`` but not
        ``marts.x.y`` (a table in a catalog that happens to be called marts) and not
        ``other.marts.cases``.
        """
        parts = table.split(".")
        for pattern in self.allow:
            wanted = pattern.split(".")
            if len(wanted) == len(parts) and all(
                fnmatch.fnmatchcase(part, want) for part, want in zip(parts, wanted, strict=True)
            ):
                return True
        return False


@dataclass(frozen=True)
class Checked:
    """A query that passed, rewritten with its row limit, ready to run."""

    sql: str
    tables: tuple[str, ...]
    limit_added: bool
    max_rows: int


def _parse(sql: str, dialect: str) -> exp.Expression:
    try:
        parsed = sqlglot.parse(sql, dialect=dialect)
        # A trailing semicolon or comment parses as an empty statement, not a second one.
        statements = [s for s in parsed if s is not None and not isinstance(s, exp.Semicolon)]
    except SqlglotError as err:
        raise Refused(Rule.PARSE, f"could not parse the query: {err}") from err
    if len(statements) != 1:
        raise Refused(
            Rule.SINGLE_STATEMENT, f"expected exactly one statement, got {len(statements)}"
        )
    return cast(exp.Expression, statements[0])


def _check_read_only(tree: exp.Expression) -> None:
    if not isinstance(tree, _READ_ROOTS):
        raise Refused(Rule.READ_ONLY, f"only SELECT queries may run, got {tree.key.upper()}")
    for node in tree.walk():
        if isinstance(node, _WRITE_NODES):
            raise Refused(Rule.READ_ONLY, f"{node.key.upper()} is not allowed inside a query")
        if isinstance(node, exp.Into):
            # SELECT ... INTO creates a table.
            raise Refused(Rule.READ_ONLY, "SELECT INTO writes a table and is not allowed")
        if isinstance(node, exp.Lock):
            raise Refused(Rule.READ_ONLY, "locking clauses (FOR UPDATE) are not allowed")
        if isinstance(node, exp.Func):
            name = (node.name or node.sql_name()).lower()
            if name in BLOCKED_FUNCTIONS:
                raise Refused(Rule.FUNCTION, f"function {name} is not allowed")
        if isinstance(node, exp.Dot) and isinstance(node.expression, exp.Func):
            package = node.this.sql().lower()
            if package.startswith(BLOCKED_PACKAGE_PREFIXES):
                called = f"{package}.{node.expression.name.lower()}"
                raise Refused(Rule.FUNCTION, f"function {called} is not allowed")


def _tables(tree: exp.Expression, policy: Policy) -> tuple[str, ...]:
    ctes = {cte.alias_or_name.lower() for cte in tree.find_all(exp.CTE)}
    found = set()
    for table in tree.find_all(exp.Table):
        name = table.name.lower()
        if not name or not isinstance(table.this, exp.Identifier):
            # A table function such as range(10), or a file path used as a table.
            raise Refused(Rule.SOURCE, "reading from table functions or files is not allowed")
        if not table.db and name in ctes:
            continue
        if not table.db:
            raise Refused(Rule.QUALIFY, f"qualify table {table.name} with its schema")
        qualified = f"{table.db.lower()}.{name}"
        if table.catalog:
            qualified = f"{table.catalog.lower()}.{qualified}"
        if not policy.allows(qualified):
            raise Refused(Rule.TABLE, f"table {qualified} is not allowed by the policy")
        found.add(qualified)
    return tuple(sorted(found))


def _check_columns(tree: exp.Expression, tables: tuple[str, ...], policy: Policy) -> None:
    if not policy.deny_columns:
        return
    table_names = {t.rsplit(".", 1)[-1] for t in tables}
    # A qualified entry applies when its table is read at all, whatever alias the query
    # gives it; that is stricter than resolving aliases and cannot be talked around.
    denied = set()
    for entry in policy.deny_columns:
        table, _, name = entry.rpartition(".")
        if not table or table.rsplit(".", 1)[-1] in table_names:
            denied.add(name)
    if not denied:
        return
    for column in tree.find_all(exp.Column):
        if column.name.lower() in denied:
            raise Refused(Rule.COLUMN, f"column {column.name} may not be read")
    # count(*) counts rows and reveals no column, so it is not a wildcard read.
    if any(not isinstance(star.parent, exp.Count) for star in tree.find_all(exp.Star)):
        hidden = ", ".join(sorted(denied))
        raise Refused(
            Rule.COLUMN, f"name the columns instead of *: these may not be read: {hidden}"
        )


def _limit(tree: exp.Expression, max_rows: int) -> tuple[exp.Expression, bool]:
    if isinstance(tree, exp.SetOperation):
        # Wrap it so the limit covers the whole result, not the last branch.
        return exp.select("*").from_(tree.subquery("q")).limit(max_rows), True
    assert isinstance(tree, exp.Select)
    existing = tree.args.get("limit")
    if existing is None:
        return tree.limit(max_rows), True
    value = existing.expression
    if not (isinstance(value, exp.Literal) and value.is_int):
        raise Refused(Rule.LIMIT, "LIMIT must be a plain number")
    if int(value.this) > max_rows:
        return tree.limit(max_rows), True
    return tree, False


def check(sql: str, policy: Policy) -> Checked:
    """Return a safe version of ``sql`` to run, or raise :class:`Refused`."""
    tree = _parse(sql, policy.dialect)
    _check_read_only(tree)
    tables = _tables(tree, policy)
    _check_columns(tree, tables, policy)
    limited, added = _limit(tree, policy.max_rows)
    return Checked(limited.sql(dialect=policy.dialect), tables, added, policy.max_rows)
