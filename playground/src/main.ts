import "@fontsource/archivo/400.css";
import "@fontsource/archivo/600.css";
import "@fontsource/archivo/800.css";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/600.css";
import "./styles.css";

import bridge from "./bridge.py?raw";
import { DEFAULT_POLICY, EXAMPLES } from "./examples";
import { createGate, parseList, parseMaxRows, type Gate, type PolicyInput, type Verdict } from "./gate";

const $ = <T extends HTMLElement>(id: string): T => {
  const el = document.getElementById(id);
  if (!el) throw new Error(`missing #${id}`);
  return el as T;
};

const allow = $<HTMLInputElement>("allow");
const deny = $<HTMLInputElement>("deny");
const maxRows = $<HTMLInputElement>("max-rows");
const sql = $<HTMLTextAreaElement>("sql");
const policyError = $("policy-error");
const verdictBox = $("verdict");
const stamp = $("stamp");
const reason = $("reason");
const detail = $("detail");
const rulebook = $("rulebook");
const runtime = $("runtime");

let gate: Gate | null = null;

allow.value = DEFAULT_POLICY.allow.join(", ");
deny.value = DEFAULT_POLICY.deny.join(", ");
maxRows.value = String(DEFAULT_POLICY.max_rows);
sql.value = EXAMPLES[0].sql;

const examples = $("examples");
for (const example of EXAMPLES) {
  const item = document.createElement("li");
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = example.label;
  button.addEventListener("click", () => {
    sql.value = example.sql;
    decide();
    sql.focus();
  });
  item.append(button);
  examples.append(item);
}

function readPolicy(): PolicyInput | string {
  const rows = parseMaxRows(maxRows.value);
  if (rows === null) return "The row limit must be a whole number above zero.";
  const tables = parseList(allow.value);
  if (!tables.length) return "List at least one table pattern, or nothing can be read.";
  return { allow: tables, deny: parseList(deny.value), max_rows: rows };
}

const el = (tag: string, className: string, text?: string): HTMLElement => {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

/** The rewritten query, with the LIMIT the gate enforced picked out. */
function rewritten(text: string): HTMLElement {
  const pre = el("pre", "runs");
  const match = /\bLIMIT \d+$/.exec(text);
  if (!match) {
    pre.textContent = text;
    return pre;
  }
  pre.append(text.slice(0, match.index), el("mark", "limit", match[0]));
  return pre;
}

function show(verdict: Verdict): void {
  detail.replaceChildren();
  for (const item of rulebook.children) item.removeAttribute("aria-current");
  if (verdict.kind === "bad-policy") {
    verdictBox.dataset.kind = "waiting";
    stamp.textContent = "Fix the rules";
    reason.textContent = verdict.message;
    return;
  }
  verdictBox.dataset.kind = verdict.kind;
  // Restart the stamp animation for each new decision.
  stamp.classList.remove("press");
  void stamp.offsetWidth;
  stamp.classList.add("press");
  if (verdict.kind === "refused") {
    stamp.textContent = "Refused";
    reason.textContent = `${verdict.message.charAt(0).toUpperCase()}${verdict.message.slice(1)}.`;
    detail.append(el("p", "rule-line", `Rule: ${verdict.rule}. The database never sees this query.`));
    document.getElementById(`rule-${verdict.rule}`)?.setAttribute("aria-current", "true");
    return;
  }
  stamp.textContent = "Allowed";
  const tables = verdict.tables.join(", ");
  reason.textContent = verdict.limit_added
    ? `It only reads ${tables}. A limit of ${verdict.max_rows.toLocaleString("en")} rows was added.`
    : `It only reads ${tables}, and returns at most ${verdict.max_rows.toLocaleString("en")} rows.`;
  detail.append(el("p", "runs-label", "What is sent to the database"), rewritten(verdict.sql));
}

function decide(): void {
  if (!gate) return;
  const policy = readPolicy();
  policyError.hidden = typeof policy !== "string";
  if (typeof policy === "string") {
    policyError.textContent = policy;
    show({ kind: "bad-policy", message: policy });
    return;
  }
  if (!sql.value.trim()) {
    show({ kind: "bad-policy", message: "Type a query to check." });
    return;
  }
  show(gate.check(policy, sql.value));
}

for (const input of [allow, deny, maxRows, sql]) input.addEventListener("input", decide);

async function start(): Promise<void> {
  // Relative to the page, not to this script, which the build moves into assets/.
  const base = new URL(".", document.baseURI).href;
  const started = performance.now();
  const { loadPyodide } = await import(/* @vite-ignore */ `${base}pyodide/pyodide.mjs`);
  const [py, names] = await Promise.all([
    loadPyodide({ indexURL: `${base}pyodide/` }),
    fetch(`${base}py/manifest.json`).then((r) => r.json() as Promise<string[]>),
  ]);
  const wheels = await Promise.all(names.map((n) => fetch(`${base}py/${n}`).then((r) => r.arrayBuffer())));
  gate = createGate(py, wheels, bridge);
  const seconds = ((performance.now() - started) / 1000).toFixed(1);
  runtime.textContent = `querygate ${gate.about.version}, running in your browser (started in ${seconds} s)`;
  runtime.dataset.ready = "true";
  for (const rule of gate.about.rules) {
    const item = el("li", "");
    item.id = `rule-${rule.id}`;
    item.append(el("span", "rule-id", rule.id), el("span", "rule-text", rule.refuses));
    rulebook.append(item);
  }
  decide();
}

start().catch((error: unknown) => {
  verdictBox.dataset.kind = "waiting";
  stamp.textContent = "Not started";
  reason.textContent = `Python could not start in this browser (${error instanceof Error ? error.message : String(error)}). Reload to try again.`;
  runtime.textContent = "Python did not start";
});
