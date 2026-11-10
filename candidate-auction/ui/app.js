// 경매 UI. 서버 문자열은 textContent 로만 넣는다. 갱신은 SSE 와 자기 요청의 응답으로 한다.
"use strict";

const STATUS_KO = { open: "진행 중", closed: "마감", settle_pending: "정산 대기" };
const auctions = new Map();   // id → 공개 정보
const cards = new Map();      // id → {root, info, msg}
let plugins = [];

// ---- 공통 ----
function el(tag, props, text) {
  const e = document.createElement(tag);
  if (props) for (const [k, v] of Object.entries(props)) {
    if (k === "class") e.className = v; else if (k === "on") {
      for (const [ev, fn] of Object.entries(v)) e.addEventListener(ev, fn);
    } else e.setAttribute(k, v);
  }
  if (text !== undefined && text !== null) e.textContent = String(text);
  return e;
}
function won(n) { return n === null || n === undefined ? "-" : n.toLocaleString("ko-KR") + "원"; }
function me() { return document.getElementById("me").value.trim(); }

async function api(method, path, body) {
  const opt = { method, headers: {} };
  if (method === "POST") {
    opt.headers["Content-Type"] = "application/json";
    opt.body = JSON.stringify(body || {});
  }
  try {
    const r = await fetch(path, opt);
    const data = await r.json();
    return { status: r.status, data };
  } catch (e) {
    return { status: 0, data: { ok: false, error: { code: "network", message: "서버에 연결할 수 없음" } } };
  }
}
function showMsg(box, res, okText) {
  box.textContent = "";
  const d = res.data;
  if (d.ok) {
    box.className = "msg ok";
    box.appendChild(document.createTextNode(okText));
  } else {
    box.className = "msg err";
    box.appendChild(document.createTextNode(`거부 (${d.error.code}): ${d.error.message}`));
  }
  if (d.trace_id) box.appendChild(traceLink(d.trace_id));
}
function traceLink(id) {
  return el("a", { class: "link", on: { click: () => openTrace(id) } }, "경로 보기");
}

// ---- 탭 ----
function switchTab(name) {
  for (const b of document.querySelectorAll(".tab")) b.classList.toggle("active", b.dataset.tab === name);
  for (const s of document.querySelectorAll(".panel")) s.classList.toggle("hidden", s.id !== "tab-" + name);
  if (name === "plugins") loadPlugins();
  if (name === "trace") loadTraces();
}
for (const b of document.querySelectorAll(".tab")) b.addEventListener("click", () => switchTab(b.dataset.tab));

// ---- 이름(탭마다 다른 사용자) ----
const meInput = document.getElementById("me");
meInput.value = sessionStorage.getItem("me") || "";
meInput.addEventListener("change", () => { sessionStorage.setItem("me", me()); loadNotifications(); });

// ---- 경매 ----
function remaining(a) {
  if (a.status !== "open") return "-";
  const s = Math.max(0, Math.ceil(a.ends_at - Date.now() / 1000));
  return s + "초";
}
function upsert(a) {
  auctions.set(a.id, a);
  renderCard(a);
}
function makeCard(a) {
  const root = el("div", { class: "card" });
  const info = el("div");
  const row = el("div", { class: "bidrow" });
  const msg = el("div", { class: "msg" });
  root.append(info, row, msg);
  const amount = el("input", { type: "number", min: "1", step: "1", placeholder: "입찰 금액(원)" });
  const btn = el("button", {}, "입찰");
  btn.addEventListener("click", async () => {
    const who = me();
    if (!who) { msg.className = "msg err"; msg.textContent = "위쪽에 내 이름을 먼저 입력하세요."; return; }
    const body = { bidder: who };
    const cur = auctions.get(a.id);
    if (cur.type !== "dutch") {
      const v = amount.value.trim();
      if (!/^\d+$/.test(v)) { msg.className = "msg err"; msg.textContent = "금액은 정수로 입력하세요."; return; }
      body.amount = parseInt(v, 10);
    }
    const res = await api("POST", `/api/auctions/${a.id}/bids`, body);
    showMsg(msg, res, `입찰 확정: ${res.data.bid ? won(res.data.bid.amount) : ""}`);
    if (res.data.ok) {
      upsert(res.data.auction);
      if (res.data.notify_error) {
        msg.className = "msg warn";
        msg.appendChild(el("div", {}, "알림 경고: " + res.data.notify_error));
      }
    }
  });
  const refresh = el("button", {}, "새로 보기");
  refresh.addEventListener("click", async () => {
    const res = await api("GET", `/api/auctions/${a.id}`);
    if (res.data.ok) upsert(res.data.auction); else showMsg(msg, res, "");
  });
  row.append(amount, btn, refresh);
  const c = { root, info, row, amount, btn, msg };
  cards.set(a.id, c);
  const list = document.getElementById("auctions");
  list.prepend(root);
  return c;
}
function renderCard(a) {
  const c = cards.get(a.id) || makeCard(a);
  const info = c.info;
  info.textContent = "";
  const title = el("div", { class: "title" });
  title.append(el("span", {}, a.item + " "), el("span", { class: "badge st-" + a.status }, STATUS_KO[a.status] || a.status));
  info.appendChild(title);
  info.appendChild(el("div", { class: "meta" },
    `방식 ${a.type} · 시작가 ${won(a.start_price)} · 현재가 ${won(a.current_price)} · 입찰 ${a.bid_count}건 · 남은 시간 `));
  info.lastChild.appendChild(el("span", { "data-remain": a.id }, remaining(a)));
  if (a.status === "closed") {
    info.appendChild(el("div", { class: "result" },
      a.winner ? `낙찰: ${a.winner} · ${won(a.price)}` : "유찰"));
  }
  if (a.status === "settle_pending") info.appendChild(el("div", { class: "reason" }, "정산 대기: " + a.reason));
  if (a.view_error) info.appendChild(el("div", { class: "reason" }, "방식 플러그인 문제: " + a.view_error));
  if (a.visible_bids && a.visible_bids.length) {
    const t = el("table");
    t.appendChild(el("tr")).append(el("th", {}, "입찰자"), el("th", {}, "금액"), el("th", {}, "시각"));
    for (const b of a.visible_bids) {
      t.appendChild(el("tr")).append(el("td", {}, b.bidder), el("td", {}, won(b.amount)),
        el("td", {}, new Date(b.created_at * 1000).toLocaleTimeString("ko-KR")));
    }
    info.appendChild(t);
  } else if (a.status === "open" && a.bid_count > 0 && a.type !== "english") {
    info.appendChild(el("div", { class: "meta" }, "비공개 방식: 마감 전에는 입찰 수만 보입니다."));
  }
  const open = a.status === "open";
  c.row.classList.toggle("hidden", !open);
  c.amount.classList.toggle("hidden", a.type === "dutch");
  c.btn.textContent = a.type === "dutch" ? "현재가 수락" : "입찰";
}
setInterval(() => {   // 남은 시간 글자만 다시 그린다(서버 조회 없음)
  for (const s of document.querySelectorAll("[data-remain]")) {
    const a = auctions.get(s.dataset.remain);
    if (a) s.textContent = remaining(a);
  }
}, 1000);

async function loadAuctions() {
  const res = await api("GET", "/api/auctions");
  if (!res.data.ok) return;
  const list = res.data.auctions.slice().reverse();  // 오래된 것부터 prepend
  for (const a of list) upsert(a);
}

document.getElementById("create").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const box = document.getElementById("create-msg");
  const sp = f.start_price.value.trim(), du = f.duration_sec.value.trim();
  if (!/^\d+$/.test(sp) || !/^\d+$/.test(du)) { box.className = "msg err"; box.textContent = "시작가·진행 시간은 정수입니다."; return; }
  const res = await api("POST", "/api/auctions", {
    item: f.item.value, start_price: parseInt(sp, 10), duration_sec: parseInt(du, 10), type: f.type.value,
  });
  showMsg(box, res, "경매를 만들었습니다.");
  if (res.data.ok) upsert(res.data.auction);
});

// ---- 알림 ----
function addNote(n, top) {
  const ul = document.getElementById("notifications");
  const li = el("li", {}, n.message);
  if (top) ul.prepend(li); else ul.appendChild(li);
}
async function loadNotifications() {
  const ul = document.getElementById("notifications");
  ul.textContent = "";
  if (!me()) return;
  const res = await api("GET", "/api/notifications?user=" + encodeURIComponent(me()));
  if (res.data.ok) for (const n of res.data.notifications) addNote(n, false);
}
function toast(text) {
  const t = document.getElementById("toast");
  t.textContent = text;
  t.classList.remove("hidden");
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => t.classList.add("hidden"), 5000);
}

// ---- 플러그인 관리 ----
async function loadPlugins() {
  const res = await api("GET", "/api/plugins");
  if (!res.data.ok) return;
  plugins = res.data.plugins;
  renderPlugins();
  renderTypeSelect();
}
function renderTypeSelect() {
  const sel = document.getElementById("type-select");
  const keep = sel.value;
  sel.textContent = "";
  for (const p of plugins) {
    if (p.kind === "auction_type" && p.state === "active") {
      sel.appendChild(el("option", { value: p.name }, `${p.name} — ${p.description}`));
    }
  }
  if ([...sel.options].some(o => o.value === keep)) sel.value = keep;
}
function renderPlugins() {
  const tb = document.querySelector("#plugins tbody");
  tb.textContent = "";
  const box = document.getElementById("plugin-msg");
  for (const p of plugins) {
    const tr = el("tr");
    const why = el("td");
    if (p.reason) why.appendChild(el("div", { class: "reason" }, p.reason));
    if (p.description) why.appendChild(el("div", { class: "desc" }, p.description));
    const ops = el("td");
    const act = async (op) => {
      const res = await api("POST", `/api/plugins/${p.name}/${op}`, {});
      showMsg(box, res, `${p.name}: ${op === "install" ? "설치됨" : "제거됨"}`);
      loadPlugins();
    };
    if (p.state !== "active") {
      ops.appendChild(el("button", { on: { click: () => act("install") } }, p.state === "disabled" ? "다시 켜기" : "설치"));
    }
    if (p.state === "active" || p.state === "disabled") {
      ops.appendChild(el("button", { on: { click: () => act("remove") } }, "제거"));
    }
    tr.append(el("td", {}, p.name), el("td", {}, p.kind || "-"), el("td", {}, p.runtime || "-"));
    const st = el("td");
    st.appendChild(el("span", { class: "badge st-" + p.state }, p.state));
    tr.append(st, el("td", {}, p.version || "-"), el("td", {}, p.generation), el("td", {}, p.failures), why, ops);
    tb.appendChild(tr);
  }
}
document.getElementById("rescan").addEventListener("click", async () => {
  const res = await api("POST", "/api/plugins/rescan", {});
  showMsg(document.getElementById("plugin-msg"), res, "다시 검색했습니다.");
  loadPlugins();
});

// ---- 요청 경로 ----
async function loadTraces() {
  const res = await api("GET", "/api/trace?limit=50");
  const ul = document.getElementById("trace-list");
  ul.textContent = "";
  if (!res.data.ok) return;
  for (const t of res.data.traces) {
    const li = el("li", { class: t.ok ? "" : "bad" },
      `${new Date(t.started_at * 1000).toLocaleTimeString("ko-KR")} ${t.label} (${t.hop_count} hop)`);
    li.dataset.id = t.trace_id;
    li.addEventListener("click", () => showTrace(t.trace_id));
    ul.appendChild(li);
  }
}
async function showTrace(id) {
  for (const li of document.querySelectorAll("#trace-list li")) li.classList.toggle("sel", li.dataset.id === id);
  const box = document.getElementById("trace-detail");
  box.textContent = "";
  const res = await api("GET", "/api/trace/" + id);
  if (!res.data.ok) { box.appendChild(el("div", { class: "msg err" }, res.data.error.message)); return; }
  const t = res.data.trace;
  box.appendChild(el("div", { class: "meta" }, `trace ${t.trace_id} · ${t.label}`));
  const tbl = el("table");
  tbl.appendChild(el("tr")).append(...["순서", "상위", "출발 → 도착", "op", "성공", "ms"].map(h => el("th", {}, h)));
  for (const h of t.hops) {
    const tr = el("tr", { class: h.ok ? "" : "hop-bad" });
    tr.append(el("td", {}, h.seq), el("td", {}, h.parent ?? "-"), el("td", {}, `${h.from} → ${h.to}`),
      el("td", {}, h.op), el("td", {}, h.ok ? "성공" : "실패"), el("td", {}, h.ms));
    tbl.appendChild(tr);
  }
  box.appendChild(tbl);
}
async function openTrace(id) {
  switchTab("trace");
  await loadTraces();
  showTrace(id);
}
document.getElementById("trace-refresh").addEventListener("click", loadTraces);

// ---- SSE ----
function connect() {
  const conn = document.getElementById("conn");
  const es = new EventSource("/api/events");
  es.onopen = () => {   // 다시 연결되면 목록을 새로 조회한다
    conn.textContent = "실시간 연결됨"; conn.className = "conn on";
    loadAuctions(); loadPlugins(); loadNotifications();
  };
  es.onerror = () => { conn.textContent = "다시 연결 중"; conn.className = "conn off"; };
  for (const t of ["auction_created", "bid_accepted", "auction_closed"]) {
    es.addEventListener(t, (ev) => {
      const a = JSON.parse(ev.data);
      upsert(a);
      if (t === "auction_closed" && a.status === "closed") {
        toast(`[${a.item}] 마감: ` + (a.winner ? `${a.winner} 낙찰 ${won(a.price)}` : "유찰"));
      }
    });
  }
  es.addEventListener("notification", (ev) => {
    const n = JSON.parse(ev.data);
    if (n.user === me()) { addNote(n, true); toast(n.message); }
  });
  es.addEventListener("plugin_changed", () => loadPlugins());
}
connect();
