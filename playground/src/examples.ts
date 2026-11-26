import type { PolicyInput } from "./gate";

export const DEFAULT_POLICY: PolicyInput = {
  allow: ["marts.*"],
  deny: ["email", "card_number"],
  max_rows: 1000,
};

export interface Example {
  label: string;
  sql: string;
  /** What querygate decides under DEFAULT_POLICY; checked by examples.test.ts. */
  expect: "allowed" | string;
}

/** Queries a model might write, each trying something different. */
export const EXAMPLES: Example[] = [
  {
    label: "A normal report",
    sql: "select region, count(*) as orders, sum(total) as revenue\nfrom marts.orders\nwhere ordered_at >= date '2026-01-01'\ngroup by region",
    expect: "allowed",
  },
  {
    label: "Delete the table's rows",
    sql: "delete from marts.orders where region = 'EU'",
    expect: "read-only",
  },
  {
    label: "Read private columns",
    sql: "select name, email, card_number\nfrom marts.customers",
    expect: "column",
  },
  {
    label: "Hide them behind *",
    sql: "select * from marts.customers",
    expect: "column",
  },
  {
    label: "Another team's table",
    sql: "select employee, salary from hr.salaries",
    expect: "table",
  },
  {
    label: "Sneak in a second statement",
    sql: "select 1; drop table marts.orders",
    expect: "single-statement",
  },
  {
    label: "Read a file from the server",
    sql: "select * from read_csv('/etc/passwd')",
    expect: "source",
  },
  {
    label: "Ask for a billion rows",
    sql: "select order_id, total from marts.orders limit 1000000000",
    expect: "allowed",
  },
];
