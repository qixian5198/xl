const API = "/api";

let personas = [];
let current = null; // {id, mode, persona}
let lastStateId = null;

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

function renderGuessPanel(mode, stateId) {
  const panel = $("guessPanel");
  const fields = $("guessFields");
  fields.innerHTML = "";
  const dims =
    mode === "mood"
      ? [
          ["情绪", ["开心", "烦躁", "焦虑", "失望", "生气", "平静"]],
          ["耐心", ["高", "中", "低"]],
          ["好感", ["高", "中", "低"]],
          ["距离感", ["疏远", "正常", "亲近"]],
        ]
      : [
          ["情绪", ["开心", "烦躁", "焦虑", "失望", "生气", "平静"]],
          ["耐心", ["高", "中", "低"]],
          ["好感", ["高", "中", "低"]],
          ["距离感", ["疏远", "正常", "亲近"]],
          ["性格", ["内向", "外向", "敏感", "强硬", "回避型", "自信", "谨慎"]],
        ];
  for (const [label, opts] of dims) {
    const sel = document.createElement("select");
    sel.dataset.key = label;
    sel.innerHTML = `<option value="">${label}</option>` + opts.map((o) => `<option>${o}</option>`).join("");
    fields.appendChild(sel);
  }
  panel.classList.remove("hidden");
  lastStateId = stateId;
}

async function sendGuess() {
  const guess = {};
  $("guessFields").querySelectorAll("select").forEach((sel) => {
    const v = sel.value;
    if (v) {
      const key = sel.dataset.key;
      const map = { 情绪: "emotion", 耐心: "patience", 好感: "affection", 距离感: "distance", 性格: "personality" };
      guess[map[key]] = v;
    }
  });
  const res = await api(`/sessions/${current.id}/guess`, {
    method: "POST",
    body: JSON.stringify({ state_id: lastStateId, guess }),
  });
  $("guessPanel").classList.add("hidden");
  lastActivity = Date.now();
  const div = addMsg("reveal", "", "feedback");
  div.innerHTML =
    `<b>实际状态</b>：${res.actual.emotion} / 耐心${res.actual.patience} / 好感${res.actual.affection} / 距离${res.actual.distance}` +
    (res.actual.personality ? ` / 性格${res.actual.personality}` : "") +
    `<br>答对 ${res.correct}/${res.total}<br><b>分析</b>：${res.analysis}`;
}

async function startSession() {
  const personaId = +$("personaSel").value;
  const mode = $("modeSel").value;
  const scene = $("sceneInput").value.trim() || null;
  const res = await api("/sessions", { method: "POST", body: JSON.stringify({ persona_id: personaId, mode, scene }) });
  current = { ...res, persona: personas.find((p) => p.id === personaId) };
  $("msgs").innerHTML = "";
  $("summary").textContent = "会话进行中…";
  $("soulBtn").disabled = false;
  $("coachBtn").disabled = false;
  $("endBtn").disabled = false;
  $("guessPanel").classList.add("hidden");
  $("inputArea").style.display = ""; // 上一会话结束后被隐藏过，恢复输入框
  $("chatTitle").textContent = `${current.persona.name} · ${$("modeSel").selectedOptions[0].text}` + (scene ? ` · ${scene}` : "");

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
  if (res.ask_user_to_guess && res.state_id) {
    renderGuessPanel(current.mode, res.state_id);
  } else {
    $("guessPanel").classList.add("hidden");
  }
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
    if (r.purpose) $("chatTitle").textContent = "对方目的：" + r.purpose + "（可据此选模式）";
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

async function endAndReview() {
  if (!confirm("结束会话并生成复盘？")) return;
  const sid = current.id;
  await api(`/sessions/${sid}/end`, { method: "POST" });
  $("endBtn").disabled = true;
  $("soulBtn").disabled = true;
  $("coachBtn").disabled = true;
  $("inputArea").style.display = "none";
  current = null;
  $("sessionSel").value = String(sid);
  await generateReview(sid);
  loadSessions();
}

async function generateReview(id) {
  $("reviewBtn").disabled = true;
  $("summary").textContent = "复盘生成中…（约需 30-90 秒）";
  try {
    const s = await api(`/sessions/${id}/summary`, { method: "POST" });
    renderSummary(s);
  } catch (e) {
    $("summary").textContent = "复盘失败：" + e.message;
  }
  $("reviewBtn").disabled = false;
}

async function viewSession(id) {
  const s = await api(`/sessions/${id}`);
  current = null; // 历史会话只读，不发消息
  $("msgs").innerHTML = "";
  $("soulBtn").disabled = true;
  $("coachBtn").disabled = true;
  $("endBtn").disabled = true;
  $("reviewBtn").disabled = false;
  $("guessPanel").classList.add("hidden");
  $("nextScenarioBtn").classList.add("hidden");
  const p = personas.find((x) => x.id === s.persona_id);
  $("chatTitle").textContent = `历史会话 #${id} · ${p ? p.name : ""} · ${s.status}`;
  $("sessionHint").textContent = `状态：${s.status}。可点右侧「生成复盘」。`;
  for (const m of s.messages) {
    if (m.role === "user") addMsg("user", m.content);
    else if (m.role === "assistant") addMsg("bot", m.content);
  }
  $("summary").textContent = "点「生成复盘」查看星级、框架、技巧点评和改进说法。";
}

function renderStars(n) {
  n = Math.max(0, Math.min(5, +n || 0));
  return "★".repeat(n) + "☆".repeat(5 - n);
}

function renderSummary(s) {
  const box = $("summary");
  box.innerHTML = "";
  const sec = (title, arr) => {
    if (!arr || !arr.length) return;
    const h = document.createElement("h3");
    h.textContent = title;
    box.appendChild(h);
    const ul = document.createElement("ul");
    for (const t of arr) {
      const li = document.createElement("li");
      li.textContent = t;
      ul.appendChild(li);
    }
    box.appendChild(ul);
  };

  // 星评 + 总分
  const score = document.createElement("div");
  score.className = "score-line";
  const stars = s.stars != null ? renderStars(s.stars) : "";
  score.textContent = `总分 ${s.total} ${stars}`;
  box.appendChild(score);

  const dims = document.createElement("div");
  dims.className = "hint";
  dims.textContent = `共情 ${s.dims?.empathy ?? "-"} · 清晰 ${s.dims?.clarity ?? "-"} · 时机 ${s.dims?.timing ?? "-"} · 尊重 ${s.dims?.respect ?? "-"} · 边界 ${s.dims?.boundary ?? "-"}`;
  box.appendChild(dims);

  // 聊天框架
  if (s.framework) {
    const fh = document.createElement("h3");
    fh.textContent = "聊天框架";
    box.appendChild(fh);
    const fd = document.createElement("div");
    fd.className = "fw-box";
    fd.textContent = s.framework;
    box.appendChild(fd);
  }

  // 公式技巧点评
  sec("公式技巧点评", s.techniques);
  sec("亮点", s.highlights);
  sec("问题", s.problems);
  sec("说话改进", s.suggestions);

  if (s.next_scenario) {
    const hint = document.createElement("div");
    hint.className = "hint";
    hint.textContent = "下次最该练：" + s.next_scenario;
    box.appendChild(hint);
    const btn = $("nextScenarioBtn");
    btn.classList.remove("hidden");
    btn.textContent = "按「" + s.next_scenario + "」再开一局";
    btn.onclick = () => {
      $("sceneInput").value = s.next_scenario;
      $("nextScenarioBtn").classList.add("hidden");
      startSession().catch((e) => alert(e.message));
    };
  } else {
    $("nextScenarioBtn").classList.add("hidden");
  }
}

async function loadSessions() {
  const rows = await api("/sessions");
  const modeNames = { mood: "判断心情", personality: "判断性格", chat: "聊天问答", soul: "灵魂提问" };
  const sel = $("sessionSel");
  sel.innerHTML =
    `<option value="">— 选历史会话复盘 —</option>` +
    rows
      .map((r) => {
        const p = personas.find((x) => x.id === r.persona_id);
        return `<option value="${r.id}">#${r.id} ${p ? p.name : ""} · ${modeNames[r.mode] || r.mode} · ${r.status}</option>`;
      })
      .join("");
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
  loadSessions();
  loadModelMini();

  $("startBtn").onclick = () => startSession().catch((e) => alert(e.message));
  $("sendBtn").onclick = () => {
    const t = $("input").value.trim();
    if (!t) return;
    if (!current) {
      alert("请先在左侧选择身份和模式，点「开始会话」再发消息。");
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

  $("guessSubmitBtn").onclick = () => sendGuess().catch((e) => alert(e.message));
  $("soulBtn").onclick = () => soulQuestion().catch((e) => alert(e.message));
  $("coachBtn").onclick = () => coachPause().catch((e) => alert(e.message));
  $("sceneRandomBtn").onclick = () => randomScene();
  $("endBtn").onclick = () => endAndReview().catch((e) => alert(e.message));
  $("reviewBtn").onclick = () => {
    const id = $("sessionSel").value;
    if (!id) { alert("请先在「历史会话」里选一个会话"); return; }
    viewSession(id).catch((e) => alert(e.message));
  };
  $("sessionSel").onchange = () => {
    const id = $("sessionSel").value;
    $("reviewBtn").disabled = !id;
    if (id) viewSession(id).catch((e) => alert(e.message));
  };
}

init();
