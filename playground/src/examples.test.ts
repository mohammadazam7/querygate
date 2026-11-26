import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { loadPyodide } from "pyodide";
import { beforeAll, describe, expect, it } from "vitest";

import { DEFAULT_POLICY, EXAMPLES } from "./examples";
import { createGate, parseList, parseMaxRows, type Gate } from "./gate";

// The same wheels and the same bridge the page uses, in the same Python runtime,
// started from Node instead of a browser. Run `npm run prepare-py` first.
const here = dirname(fileURLToPath(import.meta.url));
const py = resolve(here, "../public/py");
let gate: Gate;

beforeAll(async () => {
  const wheels = (JSON.parse(readFileSync(resolve(py, "manifest.json"), "utf-8")) as string[]).map(
    (name) => new Uint8Array(readFileSync(resolve(py, name))),
  );
  const runtime = await loadPyodide({ indexURL: resolve(here, "../node_modules/pyodide") });
  gate = createGate(runtime as never, wheels, readFileSync(resolve(here, "bridge.py"), "utf-8"));
});

describe("the real package, running in Pyodide", () => {
  it("reports its version and every rule", () => {
    expect(gate.about.version).toMatch(/^\d+\.\d+\.\d+$/);
    expect(gate.about.rules.map((r) => r.id)).toContain("read-only");
    expect(gate.about.rules.every((r) => r.refuses.length > 0)).toBe(true);
  });

  it.each(EXAMPLES.map((e) => [e.label, e] as const))("example: %s", (_label, example) => {
    const verdict = gate.check(DEFAULT_POLICY, example.sql);
    expect(verdict.kind === "refused" ? verdict.rule : verdict.kind).toBe(example.expect);
  });

  it("adds a row limit to a query without one and tightens a larger one", () => {
    const added = gate.check(DEFAULT_POLICY, "select order_id from marts.orders");
    expect(added).toMatchObject({ kind: "allowed", limit_added: true });
    const tightened = gate.check(DEFAULT_POLICY, "select order_id from marts.orders limit 1000000000");
    expect(tightened.kind === "allowed" && /LIMIT 1000$/.test(tightened.sql)).toBe(true);
  });

  it("follows the policy it is given", () => {
    const open = { allow: ["marts.*", "hr.*"], deny: [], max_rows: 50 };
    const verdict = gate.check(open, "select employee, salary from hr.salaries");
    expect(verdict).toMatchObject({ kind: "allowed", tables: ["hr.salaries"], max_rows: 50 });
  });
});

describe("reading the policy fields", () => {
  it("splits lists on commas, spaces and new lines", () => {
    expect(parseList(" marts.*, public.orders\nstaging.x ,, ")).toEqual(["marts.*", "public.orders", "staging.x"]);
    expect(parseList("   ")).toEqual([]);
  });

  it("accepts only a positive whole number of rows", () => {
    expect(parseMaxRows(" 500 ")).toBe(500);
    for (const bad of ["", "0", "-5", "1.5", "ten", "1e3"]) expect(parseMaxRows(bad)).toBeNull();
  });
});
