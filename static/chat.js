const API = "/api";

let personas = [];
let current = null; // {id, persona}
let allSkills = [];

const $ = (id) => document.getElementById(id);

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || res.status);
  return body;
}

function addMsg(role, text, cls = "") {
  const div = document.createElement("div");
  div.className = "msg " + (role === "user" ? "user" : "bot") + " " + cls;
  div.textContent = text;
  $("msgs").appendChild(div);
  $("msgs").scrollTop = $("msgs").scrollHeight;
  return div;
}

function addFeedback(fb) {
  if (!fb) return;
  const div = addMsg("feedback", "", "feedback");
  div.innerHTML = `<b>反馈 ${fb.total}</b> — 共情 ${fb.empathy} / 清晰 ${fb.clarity} / 时机 ${fb.timing} / 尊重 ${fb.respect} / 边界 ${fb.boundary}<br>${fb.comment || ""}`;
}

async function startSession() {
  const personaId = +$("personaSel").value;
  const scene = $("sceneInput").value.trim() || null;
  const res = await api("/sessions", { method: "POST", body: JSON.stringify({ persona_id: personaId, scene }) });
  current = { ...res, persona: personas.find((p) => p.id === personaId ) };
  skillPage = 1;
  $("msgs").innerHTML = "";
  $("soulBtn").disabled = false;
  $("coachBtn").disabled = false;
  $("endSessionBtn").disabled = false;
  $("endSidebarBtn").disabled = false;
  $("inputArea").style.display = ""; // 上一会话结束后被隐藏过，恢复输入框
  clearHighlight();
  $("chatTitle").textContent = current.persona.name + (scene ? ` · ${scene}` : "");

  loadSkillsForPanel().then(() => setSkillPanel(true)).catch(() => setSkillPanel(false));

  // 刷新"进行中会话"列表（新会话立刻出现）
  loadActiveSessions().catch(() => {});

  // 首条消息：发一个占位触发机器人开场
  await postMessage(`（你好，${current.persona.name}，我们开始聊。）`);
}

async function postMessage(text) {
  const mySession = current;
  addMsg("user", text);
  lastActivity = Date.now();
  const pending = addMsg("bot", "正在生成…", "pending");
  const res = await api(`/sessions/${mySession.id}/messages`, {
    method: "POST",
    body: JSON.stringify({ content: text }),
  }).catch((e) => ({ error: e.message }));
  pending.remove();
  // 等待期间切走了会话/历史会话，current 已变，丢弃这次响应（之前在这里读 current.mode 会崩）
  if (current !== mySession) return;
  if (res.error) {
    addMsg("error", "生成失败：" + res.error + "（消息已保存，可重试发送）", "feedback");
    return;
  }
  addMsg("bot", res.assistant_message);
  addFeedback(res.feedback);
  lastActivity = Date.now();
}

async function soulQuestion() {
  const res = await api(`/sessions/${current.id}/soul-question`, { method: "POST" });
  const q = res.questions.map((pair) => `• ${pair[0]}（${pair[1]}）`).join("\n");
  addMsg("soul", "灵魂提问：\n" + q, "feedback");
  lastActivity = Date.now();
}

async function coachPause() {
  if (!current) return;
  const pending = addMsg("coach", "教练点评中…", "pending");
  const res = await api(`/sessions/${current.id}/coach`, { method: "POST" }).catch((e) => ({ error: e.message }));
  pending.remove();
  if (res.error) {
    addMsg("coach", "点评失败：" + res.error, "coach-msg");
    return;
  }
  const div = addMsg("coach", "", "coach-msg");
  div.innerHTML = `<b>🧑‍🏫 暂停点评</b>${res.skill ? `（参考：${res.skill}）` : ""}<br>${res.comment}`;
  lastActivity = Date.now();
}

async function randomScene() {
  const btn = $("sceneRandomBtn");
  btn.disabled = true;
  btn.textContent = "生成中…";
  try {
    const r = await api("/scenarios/random");
    $("sceneInput").value = r.scene || "";
    $("sceneInput").placeholder = r.persona_hint ? `建议身份：${r.persona_hint}` : "可选：本次场景";
    if (r.purpose) $("chatTitle").textContent = "对方目的：" + r.purpose;
  } catch (e) {
    alert("生成场景失败：" + e.message);
  }
  btn.disabled = false;
  btn.textContent = "随机场景";
}

// ---- 静默时机器人主动搭话 ----
let lastActivity = Date.now();
let nudging = false;

async function doNudge() {
  if (!current || nudging) return;
  if (!($("nudgeOn").checked)) return;
  const min = +$("nudgeMin").value || 5;
  if (Date.now() - lastActivity < min * 60 * 1000) return;
  nudging = true;
  try {
    const res = await api(`/sessions/${current.id}/nudge`, { method: "POST" }).catch((e) => ({ error: e.message }));
    if (res.error) return; // 下一轮检查再试，不打扰用户
    addMsg("bot", res.nudge, "nudge");
    if (res.hint) addMsg("hint", "💡 " + res.hint, "hint-msg");
    lastActivity = Date.now();
  } finally {
    nudging = false;
  }
}

setInterval(doNudge, 15000);

let sessionPage = 1;
let sessionPerPage = 10;
let sessionTotal = 0;

const STATUS_NAMES = { active: "进行中", ended: "已结束" };

function fmtTime(iso) {
  if (!iso) return "";
  const d = new Date(iso.replace(" ", "T"));
  if (isNaN(d)) return iso;
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  if (d.toDateString() === now.toDateString()) return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

// 通用：一张会话卡片。active → 右上角「结束」，点击恢复会话；ended → 「✕删除」，点击查看。
function makeSessionCard(x) {
  const isActive = x.status === "active";
  const p = personas.find((y) => y.id === x.persona_id);
  const item = document.createElement("div");
  item.className = "session-item";
  item.dataset.id = String(x.id);
  const badge = document.createElement("span");
  badge.className = "s-badge " + (isActive ? "on" : "off");
  badge.textContent = STATUS_NAMES[x.status] || x.status;
  const title = document.createElement("div");
  title.className = "s-title";
  title.textContent = `${p ? p.name : "身份#" + x.persona_id}`;
  const sub = document.createElement("div");
  sub.className = "s-sub";
  sub.textContent = `#${x.id} · ${fmtTime(x.created_at)}` + (x.scene ? " · " + x.scene : "");
  item.appendChild(badge);
  item.appendChild(title);
  item.appendChild(sub);

  const actions = document.createElement("div");
  actions.className = "s-actions";
  if (isActive) {
    const endBtn = document.createElement("button");
    endBtn.className = "s-end";
    endBtn.title = "结束这条进行中会话";
    endBtn.textContent = "结束";
    endBtn.onclick = async (ev) => {
      ev.stopPropagation();
      if (!confirm(`结束进行中的会话 #${x.id}？结束后会进入历史会话。`)) return;
      try {
        await api(`/sessions/${x.id}/end`, { method: "POST" });
        if (current && current.id === x.id) resetToIdle();
        loadActiveSessions().catch(() => {});
        loadSessions().catch(() => {});
      } catch (e) { alert("结束失败：" + e.message); }
    };
    actions.appendChild(endBtn);
  } else {
    const del = document.createElement("button");
    del.className = "s-del";
    del.title = "删除这条会话";
    del.textContent = "✕";
    del.onclick = async (ev) => {
      ev.stopPropagation();
      if (!confirm(`删除历史会话 #${x.id}？聊天记录、评分都会清掉，角色/用户记忆保留。`)) return;
      try {
        await api(`/sessions/${x.id}`, { method: "DELETE" });
        loadSessions().catch(() => {});
      } catch (e) { alert("删除失败：" + e.message); }
    };
    actions.appendChild(del);
  }
  item.appendChild(actions);

  item.onclick = isActive ? () => resumeSession(x.id).catch((e) => alert(e.message)) : null;
  return item;
}

// 点击进行中的会话 → 恢复它（可继续发消息、点评、灵魂提问）
async function resumeSession(id) {
  const s = await api(`/sessions/${id}`);
  const p = personas.find((y) => y.id === s.persona_id);
  current = {
    id: s.id,
    persona_id: s.persona_id,
    status: s.status,
    scene: s.scene || "",
    skill_ids: s.skill_ids || [],
    persona: p || { id: s.persona_id, name: "身份#" + s.persona_id },
  };
  skillPage = 1;
  clearHighlight();
  $("msgs").innerHTML = "";
  $("soulBtn").disabled = false;
  $("coachBtn").disabled = false;
  $("endSessionBtn").disabled = false;
  $("endSidebarBtn").disabled = false;
  $("inputArea").style.display = "";
  $("chatTitle").textContent = `进行中 #${s.id} · ${p ? p.name : ""}`;
  loadSkillsForPanel().then(() => setSkillPanel(true)).catch(() => setSkillPanel(false));
  for (const m of s.messages) {
    if (m.role === "user") addMsg("user", m.content);
    else if (m.role === "assistant") addMsg("bot", m.content);
  }
  lastActivity = Date.now();
}

function clearHighlight() {
  document.querySelectorAll("#sessionList .session-item, #activeList .session-item").forEach((el) => {
    el.classList.remove("active");
  });
}

// 重置为「没在聊任何会话」的空闲态
function resetToIdle() {
  current = null;
  $("inputArea").style.display = "none";
  $("endSessionBtn").disabled = true;
  $("endSidebarBtn").disabled = true;
  $("soulBtn").disabled = true;
  $("coachBtn").disabled = true;
  setSkillPanel(false);
}

// ---- 技术卡（skill）手动选择 ----
function setSkillPanel(on) {
  const p = $("skillPanel");
  p.classList.toggle("hidden", !on);
  if (!on) $("skillChips").innerHTML = "";
}

function renderSkillChips(selected = []) {
  const box = $("skillChips");
  box.innerHTML = "";
  if (!allSkills.length) {
    box.innerHTML = '<span class="hint">（还没有技术卡，去设置页添加）</span>';
    return;
  }
  for (const sk of allSkills) {
    const chip = document.createElement("span");
    chip.className = "skill-chip" + (selected.includes(sk.id) ? " on" : "");
    const src = sk.source ? `<i class="skill-src">${sk.source}</i>` : "";
    chip.innerHTML = `${sk.name} ${src}`;
    chip.title = sk.do ? "该：" + sk.do : "";
    chip.onclick = () => {
      const cur = current.skill_ids ? [...current.skill_ids] : [];
      const i = cur.indexOf(sk.id);
      if (i >= 0) cur.splice(i, 1);
      else cur.push(sk.id);
      chip.classList.toggle("on", i < 0);
      persistSkills(cur);
    };
    box.appendChild(chip);
  }
}

async function persistSkills(ids) {
  if (!current) return;
  current.skill_ids = ids;
  await api(`/sessions/${current.id}/skills`, {
    method: "POST",
    body: JSON.stringify({ skill_ids: ids }),
  }).catch((e) => alert("保存技术卡选择失败：" + e.message));
}

let skillPage = 1;
const SKILLS_PER_PAGE = 6;

async function loadSkillsForPanel() {
  allSkills = await api("/skills").catch(() => []);
  renderSkillChips(current ? current.skill_ids || [] : []);
  renderSkillSidebar();
}

function renderSkillSidebar() {
  const list = $("skillSidebarList");
  list.innerHTML = "";
  $("skillCount").textContent = allSkills.length ? `共 ${allSkills.length} 张` : "";
  if (!allSkills.length) {
    list.innerHTML = '<div class="session-empty">还没有技术卡，去「⚙ 设置」添加。</div>';
    $("skillPager").classList.add("hidden");
    return;
  }
  const used = current ? current.skill_ids || [] : [];
  const pages = Math.max(1, Math.ceil(allSkills.length / SKILLS_PER_PAGE));
  skillPage = Math.min(skillPage, pages);
  const start = (skillPage - 1) * SKILLS_PER_PAGE;
  for (const sk of allSkills.slice(start, start + SKILLS_PER_PAGE)) {
    const item = document.createElement("div");
    const isOn = used.includes(sk.id);
    item.className = "skill-item" + (isOn ? " on" : "");
    item.title = "点击" + (isOn ? "取消使用" : "使用") + "该技术卡";
    const del = document.createElement("button");
    del.className = "s-del";
    del.textContent = "×";
    del.title = "删除该技术卡";
    del.onclick = async (e) => {
      e.stopPropagation();
      if (!confirm(`删除技术卡「${sk.name}」？`)) return;
      try {
        await api(`/skills/${sk.id}`, { method: "DELETE" });
        allSkills = allSkills.filter((x) => x.id !== sk.id);
        if (current && current.skill_ids.includes(sk.id)) persistSkills(current.skill_ids.filter((i) => i !== sk.id));
        renderSkillSidebar();
        renderSkillChips(current ? current.skill_ids || [] : []);
      } catch (err) { alert("删除失败：" + err.message); }
    };
    item.appendChild(del);
    if (isOn) {
      const badge = document.createElement("span");
      badge.className = "skill-used-badge";
      badge.textContent = "使用中";
      item.appendChild(badge);
    }
    const body = document.createElement("div");
    body.innerHTML =
      `<b>${sk.name}</b>${sk.source ? `<div class="skill-item-src">来源：${sk.source}</div>` : ""}` +
      (sk.triggers && sk.triggers.length ? `<div class="skill-item-desc">触发：${sk.triggers.join("、")}</div>` : "") +
      `<div class="skill-item-desc">该：${sk.do}</div>` +
      (sk.dont ? `<div class="skill-item-desc">避免：${sk.dont}</div>` : "");
    item.appendChild(body);
    item.onclick = () => {
      if (!current) {
        alert("请先在左侧「开始聊天」开启会话，再选技术卡。");
        return;
      }
      const cur = current.skill_ids ? [...current.skill_ids] : [];
      const i = cur.indexOf(sk.id);
      if (i >= 0) cur.splice(i, 1);
      else cur.push(sk.id);
      persistSkills(cur);
    };
    list.appendChild(item);
  }
  const pager = $("skillPager");
  if (pages > 1) {
    pager.classList.remove("hidden");
    $("skillPrevPage").disabled = skillPage <= 1;
    $("skillNextPage").disabled = skillPage >= pages;
    $("skillPageInfo").textContent = `${skillPage} / ${pages}`;
  } else {
    pager.classList.add("hidden");
  }
}

async function endSession() {
  if (!current) return;
  if (!confirm("结束当前会话？结束后会进入历史会话。")) return;
  const sid = current.id;
  await api(`/sessions/${sid}/end`, { method: "POST" });
  resetToIdle();
  sessionPage = 1;
  $("msgs").innerHTML = "";
  $("chatTitle").textContent = "会话已结束";
  await Promise.all([loadActiveSessions(), loadSessions()]);
}

async function loadSessions() {
  const r = await api(
    `/sessions?page=${sessionPage}&per_page=${sessionPerPage}&status=ended`
  );
  sessionTotal = r.total;
  const list = $("sessionList");
  list.innerHTML = "";

  if (!r.items.length) {
    const empty = document.createElement("div");
    empty.className = "session-empty";
    empty.textContent = "还没有历史会话，开始一局吧。";
    list.appendChild(empty);
  }

  for (const x of r.items) list.appendChild(makeSessionCard(x));

  $("histCount").textContent = sessionTotal ? `共 ${sessionTotal} 条` : "";
  const pages = Math.max(1, Math.ceil(sessionTotal / sessionPerPage));
  sessionPage = Math.min(sessionPage, pages);
  $("pageInfo").textContent = sessionTotal ? `${sessionPage} / ${pages}` : "";
  $("prevPage").disabled = sessionPage <= 1;
  $("nextPage").disabled = sessionPage >= pages;
}

async function loadActiveSessions() {
  const r = await api(`/sessions?status=active&per_page=50`);
  const list = $("activeList");
  list.innerHTML = "";
  $("activeCount").textContent = r.total ? `共 ${r.total} 条` : "";
  if (!r.items.length) {
    const empty = document.createElement("div");
    empty.className = "session-empty";
    empty.textContent = "暂无进行中的会话";
    list.appendChild(empty);
    return;
  }
  for (const x of r.items) list.appendChild(makeSessionCard(x));
}

function changePage(delta) {
  const pages = Math.max(1, Math.ceil(sessionTotal / sessionPerPage));
  const to = Math.min(Math.max(1, sessionPage + delta), pages);
  if (to === sessionPage) return;
  sessionPage = to;
  loadSessions().catch(() => {});
}

async function loadModelMini() {
  const c = await api("/config");
  $("modelMini").innerHTML = `
    <h2>当前模型</h2>
    <div class="hint">${c.model}<br>key：${c.key_masked} · 每 ${c.feedback_every_n} 轮评分<br>
    <a href="/settings.html" style="color:#3355ff">修改模型 / API Key</a></div>`;
}

async function init() {
  personas = await api("/personas");
  $("personaSel").innerHTML = personas.map((p) => `<option value="${p.id}">${p.name}（${p.occupation}/${p.relation}）</option>`).join("");
  loadSkillsForPanel().catch(() => {});
  loadActiveSessions().catch(() => {});
  loadSessions();
  loadModelMini();

  $("startBtn").onclick = () => startSession().catch((e) => alert(e.message));
  $("endSidebarBtn").onclick = () => endSession().catch((e) => alert(e.message));
  $("skillPrevPage").onclick = () => { skillPage--; renderSkillSidebar(); };
  $("skillNextPage").onclick = () => { skillPage++; renderSkillSidebar(); };
  $("sendBtn").onclick = () => {
    const t = $("input").value.trim();
    if (!t) return;
    if (!current) {
      alert("请先在左侧选择身份，点「开始会话」再发消息。");
      return;
    }
    $("input").value = "";
    postMessage(t).catch((e) => alert(e.message));
  };
  $("input").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $("sendBtn").click();
    }
  });
  $("nudgeOn").onchange = () => {
    $("nudgeLabel").textContent = $("nudgeOn").checked ? "静默时机器人会主动搭话" : "静默搭话：关";
  };
  $("nudgeMin").onchange = () => $("nudgeOn").onchange();
  $("nudgeLabel").textContent = "静默时机器人会主动搭话";

  $("soulBtn").onclick = () => soulQuestion().catch((e) => alert(e.message));
  $("coachBtn").onclick = () => coachPause().catch((e) => alert(e.message));
  $("sceneRandomBtn").onclick = () => randomScene();
  $("endSessionBtn").onclick = () => endSession().catch((e) => alert(e.message));
  $("prevPage").onclick = () => changePage(-1);
  $("nextPage").onclick = () => changePage(1);
}

init();
