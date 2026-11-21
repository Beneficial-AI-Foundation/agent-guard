// AgentGuard console: polls the local API once a second.
"use strict";

const token = new URLSearchParams(location.hash.slice(1)).get("token") || "";
let lastSeq = 0;
let labels = [];
const feed = [];
const shown = {};

// Re-render a panel only when its data changed, so buttons aren't replaced under the cursor.
function changed(name, data) {
  const key = JSON.stringify(data);
  if (shown[name] === key) return false;
  shown[name] = key;
  return true;
}

async function api(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: { "X-AgentGuard-Token": token, "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return res.json();
}

function el(tag, attrs = {}, ...children) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c !== null && c !== undefined) e.append(c instanceof Node ? c : String(c));
  }
  return e;
}

const pill = (v) => (v ? el("span", { class: `pill ${v}` }, v) : el("span", { class: "muted" }, "—"));
const time = (t) => new Date(t * 1000).toLocaleTimeString();
const label = (n) => labels[n] ?? `level ${n}`;

function why(e) {
  if (!e.verdict) return e.kind === "rules" ? `rules ${e.outcome}` : "";
  const rule = e.rule ? `rule ${e.rule}` : "";
  const reasons = {
    rule: rule, no_rule: "no rule matches", leak: "would leak", untrusted: "after outsider text",
    allowed: rule, error: e.error || "error",
  };
  return [reasons[e.cause] ?? e.cause, e.theorem ? `(${e.theorem})` : ""].join(" ");
}

function renderFeed() {
  const body = document.getElementById("feed");
  const rows = feed.filter((e) => e.tool || e.kind === "rules").slice(-200).reverse();
  if (!rows.length || !changed("feed", rows.length ? rows[0].seq : 0)) return;
  body.replaceChildren(...rows.map((e) =>
    el("tr", {},
      el("td", {}, time(e.time)),
      el("td", {}, el("code", {}, e.tool || "rules.yaml")),
      el("td", {}, pill(e.verdict)),
      el("td", {}, why(e)),
      el("td", {}, e.outcome))));
}

function renderApprovals(list) {
  if (!changed("approvals", list)) return;
  document.getElementById("approvals-section").hidden = list.length === 0;
  document.getElementById("approvals").replaceChildren(...list.map((p) => {
    const answer = async (approve) => {
      await api(`/api/approvals/${p.id}`, { method: "POST", body: JSON.stringify({ approve }) });
      refresh();
    };
    return el("div", { class: "card" },
      el("h3", {}, `${p.server}.${p.tool}`),
      el("div", {}, p.reason),
      el("pre", {}, JSON.stringify(p.arguments, null, 2)),
      p.context.length
        ? el("div", {}, el("div", { class: "muted" }, "Outsider text the agent read before this:"),
            ...p.context.map((t) => el("pre", { class: "context" }, t)))
        : null,
      el("div", { class: "actions" },
        el("button", { class: "approve", onclick: () => answer(true) }, "Approve"),
        el("button", { class: "reject", onclick: () => answer(false) }, "Reject")));
  }));
}

function renderStatus(s) {
  labels = s.labels;
  if (!changed("status", s)) return;
  document.getElementById("status").textContent =
    `${s.servers.join(", ")} · ${s.tools} tools · mode ${s.mode} · rules ${s.policy}`;
  const sessions = document.getElementById("sessions");
  if (s.sessions.length) {
    sessions.replaceChildren(el("div", { class: "kv" }, ...s.sessions.map((x) =>
      el("div", {},
        el("span", {}, el("code", {}, x.key), ` · ${x.calls} calls`),
        el("span", {},
          `read up to ${label(x.level)}`, x.tainted ? " · read outsider text " : " ",
          el("button", {
            onclick: async () => { await api(`/api/sessions/${x.key}/end`, { method: "POST" }); refresh(); },
          }, "End session"))))));
  }
  document.getElementById("proofs").replaceChildren(el("div", { class: "kv" },
    el("div", {}, el("span", {}, "Decision worker"), el("code", {}, s.worker)),
    el("div", {}, el("span", {}, `${s.theorems.length} theorems proved in Lean`)),
    el("ul", {}, ...s.theorems.map((t) => el("li", {}, el("code", {}, t))))));
  document.getElementById("rules-meta").textContent =
    `${s.rules.length} rules · labels ${s.labels.join(" < ")} · first match wins, no match means deny`;
  document.getElementById("rules").replaceChildren(...s.rules.map((r, i) =>
    el("tr", {},
      el("td", {}, i + 1),
      el("td", {}, el("code", {}, r.tool)),
      el("td", {}, el("code", {}, r.when ? JSON.stringify(r.when) : "")),
      el("td", {}, pill(r.action)),
      el("td", {}, r.effect ?? "readwrite"),
      el("td", {}, r.source ?? "untrusted"),
      el("td", {}, r.impact ?? "high"))));
}

async function refresh() {
  try {
    const [status, events, approvals] = await Promise.all([
      api("/api/status"), api(`/api/events?since=${lastSeq}`), api("/api/approvals"),
    ]);
    renderStatus(status);
    feed.push(...events.events);
    lastSeq = events.last;
    renderFeed();
    renderApprovals(approvals);
  } catch (err) {
    document.getElementById("status").textContent = `Not connected (${err.message})`;
  }
}

document.getElementById("token-missing").hidden = Boolean(token);
refresh();
setInterval(refresh, 1000);
