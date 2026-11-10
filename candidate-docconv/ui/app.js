// 서버가 준 문자열은 textContent 로만 넣는다.
"use strict";

const $ = (id) => document.getElementById(id);

// 경고 {plugin, code, message} 를 한 줄 문장으로
function warnText(w) {
  return typeof w === "string" ? w : `${w.plugin} (${w.code}): ${w.message}`;
}

function el(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined && text !== null) e.textContent = String(text);
  if (cls) e.className = cls;
  return e;
}

function showMsg(text, ok) {
  const m = $("msg");
  m.textContent = text;
  m.className = ok ? "msg ok" : "msg";
  m.hidden = !text;
}

async function api(method, path, body, headers) {
  let res;
  try {
    res = await fetch(path, { method, body, headers });
  } catch (e) {
    return { ok: false, error: { code: "network", message: "서버에 연결할 수 없습니다." } };
  }
  try {
    return await res.json();
  } catch (e) {
    return { ok: false, error: { code: "http", message: "응답을 읽을 수 없습니다(HTTP " + res.status + ")." } };
  }
}

function errText(r) {
  return r.error ? r.error.message + " (" + r.error.code + ")" : "알 수 없는 오류";
}

// 탭 ---------------------------------------------------------------------
function openTab(name) {
  document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".panel").forEach((p) => (p.hidden = p.id !== "tab-" + name));
  if (name === "domain") { loadPosts(); loadHistory(); }
  if (name === "plugins") loadPlugins();
  if (name === "trace") loadTraces();
}
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => openTab(b.dataset.tab)));

// 변환 화면 ---------------------------------------------------------------
async function loadPosts() {
  const r = await api("GET", "/api/plugins");
  const box = $("posts");
  const checked = new Set([...box.querySelectorAll("input:checked")].map((i) => i.value));
  box.replaceChildren(el("legend", "후처리"));
  if (!r.ok) { box.appendChild(el("span", errText(r), "reason")); return; }
  const posts = r.plugins.filter((p) => p.kind === "postprocessor" && p.state === "active")
    .sort((a, b) => a.order - b.order);
  if (!posts.length) box.appendChild(el("span", "켜진 후처리기가 없습니다.", "hint"));
  for (const p of posts) {
    const lab = el("label");
    const cb = el("input");
    cb.type = "checkbox";
    cb.value = p.name;
    cb.checked = checked.has(p.name);
    lab.append(cb, " " + (p.description || p.name) + " (" + p.name + ", order " + p.order + ")");
    box.appendChild(lab);
  }
}

function selectedPosts() {
  return [...$("posts").querySelectorAll("input:checked")].map((i) => i.value).join(",");
}

function download(id) {
  const a = document.createElement("a");
  a.href = "/api/files/" + id + ".md";
  a.download = "";
  document.body.appendChild(a);
  a.click();
  a.remove();
}

function traceButton(tid) {
  const b = el("button", "경로 보기", "small");
  b.addEventListener("click", () => { openTab("trace"); showTrace(tid); });
  return b;
}

function resultCard(name, r) {
  const card = el("div", null, r.ok ? "card" : "card fail");
  const head = el("div", null, "head");
  head.appendChild(el("strong", r.ok ? r.filename : name));
  if (r.ok) {
    head.appendChild(el("span", r.format + " · " + r.converter + " · " + r.ms + " ms", "hint"));
    const dl = el("button", ".md 내려받기", "small");
    dl.addEventListener("click", () => download(r.id));
    head.appendChild(dl);
  } else {
    head.appendChild(el("span", "실패: " + errText(r), "reason"));
  }
  if (r.trace_id) head.appendChild(traceButton(r.trace_id));
  card.appendChild(head);
  for (const w of r.warnings || []) card.appendChild(el("div", "경고: " + warnText(w), "warn"));
  if (r.ok) card.appendChild(el("pre", r.markdown));
  return card;
}

async function sendFiles(files) {
  const box = $("results");
  if (box.querySelector(".hint")) box.replaceChildren();
  for (const f of files) {  // 하나씩 차례로 보낸다
    if (f.size > 20 * 1024 * 1024) {
      box.prepend(resultCard(f.name, { ok: false, error: { code: "too_large", message: "파일이 20MB 를 넘습니다." } }));
      continue;
    }
    showMsg(f.name + " 변환 중…", true);
    const headers = { "X-Filename": encodeURIComponent(f.name), "Content-Type": "application/octet-stream" };
    const posts = selectedPosts();
    if (posts) headers["X-Post"] = posts;
    const r = await api("POST", "/api/convert", f, headers);
    box.prepend(resultCard(f.name, r));
  }
  showMsg("");
  loadHistory();
}

const drop = $("drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.classList.add("over"); });
drop.addEventListener("dragleave", () => drop.classList.remove("over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.classList.remove("over");
  sendFiles([...e.dataTransfer.files]);
});
$("file").addEventListener("change", (e) => { sendFiles([...e.target.files]); e.target.value = ""; });

async function loadHistory() {
  const r = await api("GET", "/api/history");
  const tb = $("history");
  tb.replaceChildren();
  if (!r.ok) { showMsg("기록을 불러오지 못했습니다: " + errText(r)); return; }
  for (const h of r.items) {
    const tr = el("tr");
    tr.append(el("td", h.at), el("td", h.filename), el("td", h.format || "-"), el("td", h.converter || "-"),
      el("td", h.ms));
    tr.appendChild(el("td", h.ok ? "성공" : "실패: " + h.reason, h.ok ? "ok-yes" : "ok-no"));
    tr.appendChild(el("td", (h.warnings || []).map(warnText).join(" / "), "warn"));
    const act = el("td");
    if (h.ok && h.id) {
      const b = el("button", "내려받기", "small");
      b.addEventListener("click", () => download(h.id));
      act.appendChild(b);
    }
    if (h.trace_id) act.appendChild(traceButton(h.trace_id));
    tr.appendChild(act);
    tb.appendChild(tr);
  }
}
$("reload-history").addEventListener("click", loadHistory);

// 플러그인 관리 -----------------------------------------------------------
async function pluginAction(name, action) {
  const r = await api("POST", "/api/plugins/" + name + "/" + action);
  if (r.ok) showMsg(name + ": " + (action === "install" ? "설치됨" : "제거됨"), true);
  else showMsg(name + " " + (action === "install" ? "설치" : "제거") + " 실패: " + errText(r));
  loadPlugins();
}

async function loadPlugins() {
  const r = await api("GET", "/api/plugins");
  const tb = $("plugins");
  tb.replaceChildren();
  if (!r.ok) { showMsg("목록을 불러오지 못했습니다: " + errText(r)); return; }
  for (const p of r.plugins) {
    const tr = el("tr");
    tr.append(el("td", p.name), el("td", p.kind || "-"), el("td", p.runtime));
    const st = el("td");
    st.appendChild(el("span", p.state, "state state-" + p.state));
    tr.append(st, el("td", p.version || "-"), el("td", p.generation), el("td", p.failures));
    tr.appendChild(el("td", Array.isArray(p.formats) ? p.formats.join(", ") : (p.order !== null && p.order !== undefined ? "order " + p.order : "-")));
    const desc = el("td");
    desc.appendChild(el("div", p.description || ""));
    if (p.reason) desc.appendChild(el("div", "사유: " + p.reason, "reason"));
    tr.appendChild(desc);
    const act = el("td");
    const label = p.state === "disabled" ? "다시 켜기" : p.state === "active" ? "다시 설치" : "설치";
    const ins = el("button", label, "small");
    ins.addEventListener("click", () => pluginAction(p.name, "install"));
    act.appendChild(ins);
    if (p.state === "active" || p.state === "disabled") {
      const rm = el("button", "제거", "small");
      rm.addEventListener("click", () => pluginAction(p.name, "remove"));
      act.appendChild(rm);
    }
    tr.appendChild(act);
    tb.appendChild(tr);
  }
}
$("rescan").addEventListener("click", async () => {
  const r = await api("POST", "/api/plugins/rescan");
  if (r.ok) showMsg("다시 검색: 추가 " + r.added.length + "개 (" + r.added.join(", ") + "), 빠짐 " + r.dropped.length + "개", true);
  else showMsg("다시 검색 실패: " + errText(r));
  loadPlugins();
});

// 요청 경로 ---------------------------------------------------------------
let selectedTrace = null;

async function loadTraces() {
  const r = await api("GET", "/api/trace?limit=50");
  const ul = $("trace-list");
  ul.replaceChildren();
  if (!r.ok) { showMsg("경로 목록을 불러오지 못했습니다: " + errText(r)); return; }
  if (!r.traces.length) ul.appendChild(el("li", "아직 기록된 요청이 없습니다.", "hint"));
  for (const t of r.traces) {
    const li = el("li", t.at + "  " + t.label + "  " + (t.ok ? "성공" : "실패") + "  " + t.ms + " ms");
    if (t.trace_id === selectedTrace) li.classList.add("sel");
    li.addEventListener("click", () => showTrace(t.trace_id));
    ul.appendChild(li);
  }
}
$("reload-trace").addEventListener("click", loadTraces);

async function showTrace(tid) {
  selectedTrace = tid;
  const r = await api("GET", "/api/trace/" + tid);
  const tb = $("hops");
  tb.replaceChildren();
  if (!r.ok) { $("trace-title").textContent = "경로를 찾을 수 없습니다: " + errText(r); return; }
  $("trace-title").textContent = r.trace.label + " · " + tid;
  for (const h of r.trace.hops) {
    const tr = el("tr");
    tr.append(el("td", h.seq), el("td", h.parent === null ? "-" : h.parent),
      el("td", h.from + " → " + h.to), el("td", h.op));
    tr.appendChild(el("td", h.ok ? "성공" : "실패", h.ok ? "ok-yes" : "ok-no"));
    tr.appendChild(el("td", h.ms));
    tb.appendChild(tr);
  }
  loadTraces();
}

openTab("domain");
