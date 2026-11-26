/** Types and helpers shared by the page and its tests. The checking itself is Python. */

export interface PolicyInput {
  allow: string[];
  deny: string[];
  max_rows: number;
}

export type Verdict =
  | { kind: "allowed"; sql: string; tables: string[]; limit_added: boolean; max_rows: number }
  | { kind: "refused"; rule: string; message: string }
  | { kind: "bad-policy"; message: string };

export interface About {
  version: string;
  rules: { id: string; refuses: string }[];
}

/** What the page needs from a running Python: answer one request. */
export interface Gate {
  about: About;
  check(policy: PolicyInput, sql: string): Verdict;
}

interface PyRuntime {
  unpackArchive(buffer: ArrayBuffer | Uint8Array, format: string): void;
  runPython(code: string): unknown;
  globals: { get(name: string): (arg?: string) => string };
}

/** Install the wheels into a loaded Pyodide and wrap the two bridge functions. */
export function createGate(py: PyRuntime, wheels: (ArrayBuffer | Uint8Array)[], bridge: string): Gate {
  for (const wheel of wheels) py.unpackArchive(wheel, "wheel");
  py.runPython(bridge);
  const run = py.globals.get("run");
  const about = JSON.parse(py.globals.get("about")()) as About;
  return {
    about,
    check: (policy, sql) => JSON.parse(run(JSON.stringify({ ...policy, sql }))) as Verdict,
  };
}

/** "marts.*, public.orders" or one per line, to a clean list. */
export function parseList(text: string): string[] {
  return text
    .split(/[\s,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

export function parseMaxRows(text: string): number | null {
  if (!/^\d+$/.test(text.trim())) return null;
  const n = Number(text);
  return Number.isSafeInteger(n) && n > 0 ? n : null;
}
