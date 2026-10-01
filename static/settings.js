const API = "/api";

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || res.status);
  return body;
}

const $ = (id) => document.getElementById(id);

async function loadConfig() {
  const c = await api("/config");
  $("cfgBaseUrl").value = c.base_url || "";
  $("cfgKey").value = "";
  $("cfgKeyHint").textContent = "当前 key：" + c.key_masked;
  $("cfgModel").value = c.model || "";
  $("cfgTimeout").value = c.timeout;
  $("cfgRetries").value = c.retries;
  $("cfgN").value = c.feedback_every_n;
}

async function refreshModels() {
  $("modelsBtn").disabled = true;
  $("cfgStatus").textContent = "正在拉取模型列表…";
  try {
    const r = await api("/models");
    const dl = $("modelList");
    dl.innerHTML = r.models.map((m) => `<option value="${m}">`).join("");
    $("cfgStatus").textContent = `已加载 ${r.models.length} 个模型，从下拉里选或直接手输。`;
  } catch (e) {
    $("cfgStatus").textContent = "拉取模型列表失败：" + e.message;
  }
  $("modelsBtn").disabled = false;
}

async function saveConfig() {
  const body = {
    base_url: $("cfgBaseUrl").value.trim() || null,
    api_key: $("cfgKey").value.trim() || null,
    model: $("cfgModel").value.trim() || null,
    timeout: +$("cfgTimeout").value || null,
    retries: +$("cfgRetries").value || null,
    feedback_every_n: +$("cfgN").value || null,
  };
  const c = await api("/config", { method: "POST", body: JSON.stringify(body) });
  $("cfgKey").value = "";
  $("cfgKeyHint").textContent = "当前 key：" + c.key_masked;
  $("cfgStatus").textContent = "已保存。";
}

async function testConfig() {
  $("testCfgBtn").disabled = true;
  $("cfgStatus").textContent = "测试中…";
  try {
    await api("/config/test", { method: "POST" });
    $("cfgStatus").textContent = "连通正常 ✓";
  } catch (e) {
    $("cfgStatus").textContent = "测试失败：" + e.message;
  }
  $("testCfgBtn").disabled = false;
}

async function loadUser() {
  const users = await api("/users");
  const u = users[0];
  if (!u) return;
  $("uName").value = u.name || "";
  $("uWork").value = u.work_context || "";
  $("uEmo").value = u.emotional_context || "";
  $("uLife").value = u.life_context || "";
}

async function saveUser() {
  const users = await api("/users");
  if (!users.length) return;
  await api(`/users/${users[0].id}`, {
    method: "PUT",
    body: JSON.stringify({
      name: $("uName").value || null,
      work_context: $("uWork").value || null,
      emotional_context: $("uEmo").value || null,
      life_context: $("uLife").value || null,
    }),
  });
  alert("资料已保存");
}

// ---- 人员身份管理（字段参考 人员身份字段.md）----
const SELECTS = {
  gender: ["男", "女", "不明确"],
  education: ["高中", "本科", "硕士", "博士", "不明确"],
  income: ["低", "中", "高", "不明确"],
  relation: ["陌生人", "网友", "朋友", "同事", "领导", "下属", "亲戚", "恋人", "同学", "客户"],
  marriage: ["未婚", "恋爱中", "已婚", "离异", "丧偶"],
  familyRel: ["亲密", "疏远", "矛盾", "复杂"],
  familyEdu: ["严格", "宽松", "重成绩", "重人情"],
  extIntro: ["外向", "内向"],
  direct: ["直接", "委婉"],
  think: ["理性", "感性"],
  emoStable: ["稳定", "情绪化"],
  active: ["主动", "被动"],
  risk: ["谨慎", "冒险"],
  humorLevel: ["无", "低", "中", "高"],
  sensitive: ["高", "中", "低"],
  trait: ["高", "中", "低"],
  power: ["对方高于我", "平级", "对方低于我"],
  purpose: ["闲聊", "求助", "求安慰", "试探", "谈判", "吵架"],
  termLevel: ["高", "中", "低"],
  exprLevel: ["高", "中", "低"],
  learnLevel: ["高", "中", "低"],
};

// 表单结构：group → 字段（key 对应内部；sliders 为 0-10）
const FORM_DEF = [
  {
    group: "基础身份",
    fields: [
      { key: "name", label: "姓名", type: "text", required: true, placeholder: "如：李医生 / 老王" },
      { key: "age", label: "年龄", type: "text", placeholder: "如：35" },
      { key: "gender", label: "性别", type: "select", options: "gender" },
      { key: "education", label: "学历", type: "select", options: "education" },
      { key: "occupation", label: "职业", type: "text", required: true, placeholder: "医生 / 程序员 / 销售" },
      { key: "years", label: "工作年限", type: "text", placeholder: "如：8 年" },
      { key: "income", label: "收入水平", type: "select", options: "income" },
      { key: "city", label: "城市 / 地区", type: "text" },
      { key: "relation", label: "与你（用户）的关系", type: "select", options: "relation", required: true },
      { key: "tone", label: "语气风格", type: "text", required: true, placeholder: "如：稳重直接，不爱绕弯" },
      { key: "style", label: "沟通风格", type: "text", placeholder: "如：爱反问 / 短句 / 爱岔开话题 / 爱讲道理" },
      { key: "humor", label: "幽默风格", type: "text", placeholder: "如：偶尔冷幽默" },
      { key: "background", label: "背景故事", type: "text", placeholder: "经历、工作状况等" },
    ],
  },
  {
    group: "家庭背景",
    fields: [
      { key: "marriage", label: "婚姻状态", type: "select", options: "marriage" },
      { key: "children", label: "子女", type: "text", placeholder: "如：一女儿，8 岁" },
      { key: "parents", label: "父母情况", type: "text", placeholder: "如：母亲身体不好" },
      { key: "familyRel", label: "家庭关系", type: "select", options: "familyRel" },
      { key: "familyPressure", label: "家庭压力", type: "text", placeholder: "房贷 / 教育 / 催婚 / 亲戚比较…" },
      { key: "familyEdu", label: "家教氛围", type: "select", options: "familyEdu" },
    ],
  },
  {
    group: "性格",
    fields: [
      { key: "extIntro", label: "外向 / 内向", type: "select", options: "extIntro" },
      { key: "direct", label: "直接 / 委婉", type: "select", options: "direct" },
      { key: "think", label: "理性 / 感性", type: "select", options: "think" },
      { key: "emoStable", label: "稳定 / 情绪化", type: "select", options: "emoStable" },
      { key: "active", label: "主动 / 被动", type: "select", options: "active" },
      { key: "risk", label: "谨慎 / 冒险", type: "select", options: "risk" },
      { key: "sensitive", label: "敏感度（对玩笑、评价、冷落的反应）", type: "select", options: "sensitive" },
    ],
  },
  {
    group: "人品 / 价值观（各填 高 / 中 / 低）",
    fields: ["诚信", "责任心", "边界感", "同理心", "占有欲", "公平感", "面子观", "忠诚度"].map((k) => ({
      key: k, label: k, type: "select", options: "trait",
    })),
  },
  {
    group: "社交关系",
    fields: [
      { key: "familiarity", label: "熟悉度", type: "slider", max: 10 },
      { key: "power", label: "权力关系", type: "select", options: "power" },
      { key: "trust", label: "信任度", type: "slider", max: 10 },
      { key: "purpose", label: "聊天目的", type: "select", options: "purpose" },
    ],
  },
  {
    group: "知识 / 能力",
    fields: [
      { key: "expertise", label: "专业领域（逗号分隔）", type: "text", placeholder: "如：中医内科，方剂" },
      { key: "termLevel", label: "术语水平", type: "select", options: "termLevel" },
      { key: "lifeExp", label: "生活经验", type: "text", placeholder: "情感 / 人情世故 / 职场" },
      { key: "exprLevel", label: "表达能力", type: "select", options: "exprLevel" },
      { key: "learnLevel", label: "学习意愿", type: "select", options: "learnLevel" },
    ],
  },
];

// 分组 → profile 里的键
const PROFILE_GROUPS = {
  家庭背景: ["marriage", "children", "parents", "familyRel", "familyPressure", "familyEdu"],
  性格: ["extIntro", "direct", "think", "emoStable", "active", "risk", "sensitive"],
  "人品 / 价值观（各填 高 / 中 / 低）": ["诚信", "责任心", "边界感", "同理心", "占有欲", "公平感", "面子观", "忠诚度"],
  社交关系: ["familiarity", "power", "trust", "purpose"],
  "知识 / 能力": ["termLevel", "lifeExp", "exprLevel", "learnLevel"],
};
const PROFILE_LABELS = {
  marriage: "婚姻状态", children: "子女", parents: "父母", familyRel: "家庭关系",
  familyPressure: "家庭压力", familyEdu: "家教氛围",
  extIntro: "内外向", direct: "表达方式", think: "思维", emoStable: "情绪",
  active: "主动性", risk: "决策风格", sensitive: "敏感度",
  familiarity: "熟悉度", power: "权力关系", trust: "信任度", purpose: "聊天目的",
  termLevel: "术语水平", lifeExp: "生活经验", exprLevel: "表达能力", learnLevel: "学习意愿",
  诚信: "诚信", 责任心: "责任心", 边界感: "边界感", 同理心: "同理心",
  占有欲: "占有欲", 公平感: "公平感", 面子观: "面子观", 忠诚度: "忠诚度",
};

let personaFormKey = "new"; // 或 pid 数字

function buildForm(p) {
  p = p || {};
  const container = $("personaForm");
  container.classList.remove("hidden");
  container.innerHTML = "";
  const heading = document.createElement("h3");
  heading.textContent = p.id ? `编辑：${p.name}` : "新人员资料";
  container.appendChild(heading);

  for (const gd of FORM_DEF) {
    const g = document.createElement("div");
    g.className = "p-group";
    const gt = document.createElement("h4");
    gt.textContent = gd.group;
    g.appendChild(gt);
    const grid = document.createElement("div");
    grid.className = "p-grid";
    for (const f of gd.fields) {
      const cell = document.createElement("div");
      const lab = document.createElement("label");
      lab.textContent = f.label + (f.required ? " *" : "");
      cell.appendChild(lab);
      let el;
      if (f.type === "select") {
        el = document.createElement("select");
        el.innerHTML = `<option value="">—</option>` + SELECTS[f.options].map((o) => `<option>${o}</option>`).join("");
      } else if (f.type === "slider") {
        el = document.createElement("input");
        el.type = "range";
        el.min = "0";
        el.max = String(f.max || 10);
        el.value = String(f.value ?? (f.max || 10) / 2);
        el.style.margin = "4px 0";
        cell.appendChild(el);
        const sv = document.createElement("span");
        sv.className = "hint";
        sv.textContent = el.value;
        el.oninput = () => (sv.textContent = el.value);
        cell.appendChild(sv);
      } else {
        el = document.createElement("input");
        el.type = "text";
        el.placeholder = f.placeholder || "";
      }
      el.dataset.key = f.key;
      el.dataset.group = gd.group;
      cell.appendChild(el);
      grid.appendChild(cell);
    }
    g.appendChild(grid);
    container.appendChild(g);
  }

  // 回填
  const put = (k, v) => { const el = container.querySelector(`[data-key="${CSS.escape(k)}"]`); if (el && v != null) el.value = v; };
  put("expertise", (p.expertise || []).join("，"));
  if (p.profile) {
    for (const [group, keys] of Object.entries(PROFILE_GROUPS)) {
      const label = group === "人品 / 价值观（各填 高 / 中 / 低）" ? "人品 / 价值观" : group;
      const prof = p.profile[label] || p.profile[group] || {};
      for (const k of keys) put(k, prof[PROFILE_LABELS[k]] ?? prof[k]);
    }
    const basic = p.profile["基础身份"] || {};
    for (const k of ["education", "years", "income", "city"]) {
      const map = { 学历: "education", 工作年限: "years", 收入水平: "income", 城市地区: "city" };
      for (const [cnKey, fk] of Object.entries(map)) if (basic[cnKey]) put(fk, basic[cnKey]);
    }
  }
  put("name", p.name || ""); put("age", (p.age_group || "").replace(/未知|岁/g, "") || "");
  put("gender", p.gender || "");
  put("occupation", p.occupation || ""); put("relation", p.relation || "");
  put("tone", p.tone || ""); put("humor", p.humor || ""); put("style", p.style || ""); put("background", p.background || "");

  const btnRow = document.createElement("div");
  btnRow.className = "row";
  const saveB = document.createElement("button");
  saveB.textContent = p.id ? "保存修改" : "创建人员";
  const cancelB = document.createElement("button");
  cancelB.className = "ghost";
  cancelB.textContent = "取消";
  cancelB.style.width = "auto";
  cancelB.onclick = () => { container.classList.add("hidden"); loadPersonas(); };
  btnRow.appendChild(saveB);
  btnRow.appendChild(cancelB);
  container.appendChild(btnRow);

  saveB.onclick = async () => {
    const get = (k) => {
      const el = container.querySelector(`[data-key="${CSS.escape(k)}"]`);
      return el ? String(el.value).trim() : "";
    };
    const body = {
      name: get("name"),
      age_group: get("age") ? get("age") + " 岁" : "未知",
      gender: get("gender") || "不明确",
      occupation: get("occupation"),
      relation: get("relation"),
      tone: get("tone"),
      humor: get("humor") || null,
      style: get("style") || null,
      background: get("background") || "",
      expertise: get("expertise").split(/[，,]/).map((x) => x.trim()).filter(Boolean),
    };
    if (!body.name || !body.occupation || !body.relation || !body.tone) {
      alert("姓名、职业、与你关系、语气风格为必填项");
      return;
    }
    // 组装 profile
    const profile = {};
    const add = (group, key) => {
      const v = get(key);
      if (v) {
        profile[group] = profile[group] || {};
        profile[group][PROFILE_LABELS[key] || key] = v;
      }
    };
    for (const [group, keys] of Object.entries(PROFILE_GROUPS)) {
      const label = group === "人品 / 价值观（各填 高 / 中 / 低）" ? "人品 / 价值观" : group;
      for (const k of keys) add(label, k);
    }
    // 基础身份里进 profile 的补充字段
    const basic = {};
    for (const k of ["education", "years", "income", "city"]) {
      const v = get(k);
      const map = { education: "学历", years: "工作年限", income: "收入水平", city: "城市地区" };
      if (v) basic[map[k]] = v;
    }
    if (Object.keys(basic).length) profile["基础身份"] = { ...(profile["基础身份"] || {}), ...basic };
    // 知识能力
    const kexp = {};
    for (const k of ["termLevel", "lifeExp", "exprLevel", "learnLevel"]) {
      const v = get(k);
      if (v) kexp[PROFILE_LABELS[k]] = v;
    }
    if (Object.keys(kexp).length) profile["知识 / 能力"] = { ...(profile["知识 / 能力"] || {}), ...kexp };
    body.profile = Object.keys(profile).length ? profile : null;

    try {
      if (p.id) await api(`/personas/${p.id}`, { method: "PUT", body: JSON.stringify(body) });
      else await api("/personas", { method: "POST", body: JSON.stringify(body) });
      container.classList.add("hidden");
      loadPersonas();
    } catch (e) {
      alert("保存失败：" + e.message);
    }
  };
  container.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function loadPersonas() {
  const rows = await api("/personas");
  const list = $("personaList");
  list.innerHTML = "";
  for (const p of rows) {
    const item = document.createElement("div");
    item.className = "persona-item";
    const info = document.createElement("div");
    info.innerHTML = `<b>${p.name}</b>（${p.occupation}/${p.relation}）` +
      `<div class="hint">${p.tone || ""} ${p.humor ? "· " + p.humor : ""}</div>`;
    const btns = document.createElement("div");
    btns.className = "row";
    const eb = document.createElement("button");
    eb.className = "ghost";
    eb.style.width = "auto";
    eb.textContent = "编辑";
    eb.onclick = () => buildForm(p);
    const db = document.createElement("button");
    db.className = "ghost";
    db.style.width = "auto";
    db.style.color = "#d4380d";
    db.style.borderColor = "#d4380d";
    db.textContent = "删除";
    db.onclick = async () => {
      if (!confirm(`删除 ${p.name}？`)) return;
      await api(`/personas/${p.id}`, { method: "DELETE" });
      loadPersonas();
    };
    btns.appendChild(eb);
    btns.appendChild(db);
    item.appendChild(info);
    item.appendChild(btns);
    list.appendChild(item);
  }
}

// 修补 PERSONA 表单里"人品"分组的标签映射（保证 profile 里中文键一致）
PROFILE_GROUPS["人品 / 价值观（各填 高 / 中 / 低）"] = ["诚信", "责任心", "边界感", "同理心", "占有欲", "公平感", "面子观", "忠诚度"];
for (const k of ["诚信", "责任心", "边界感", "同理心", "占有欲", "公平感", "面子观", "忠诚度"]) {
  PROFILE_LABELS[k] = k;
}

// ---- 沟通技术卡（skill）管理 ----
async function loadSkills() {
  const rows = await api("/skills");
  const list = $("skillList");
  list.innerHTML = "";
  if (!rows.length) {
    list.innerHTML = '<div class="hint">暂无技术卡。点「＋ 添加技术卡」或「粘贴导入多张卡」。</div>';
  }
  for (const sk of rows) {
    const item = document.createElement("div");
    item.className = "persona-item";
    const info = document.createElement("div");
    info.innerHTML = `<b>${sk.name}</b>${sk.source ? "（" + sk.source + "）" : ""}` +
      `<div class="hint">触发：${(sk.triggers || []).join("、") || "—"}<br>该：${sk.do}<br>避免：${sk.dont || "—"}</div>`;
    const btns = document.createElement("div");
    btns.className = "row";
    const del = document.createElement("button");
    del.className = "ghost";
    del.style.width = "auto";
    del.style.color = "#d4380d";
    del.style.borderColor = "#d4380d";
    del.textContent = "删除";
    del.onclick = async () => {
      if (!confirm("删除技术卡「" + sk.name + "」？")) return;
      await api(`/skills/${sk.id}`, { method: "DELETE" });
      loadSkills();
    };
    btns.appendChild(del);
    item.appendChild(info);
    item.appendChild(btns);
    list.appendChild(item);
  }
}

function showSkillForm() {
  const f = $("skillForm");
  f.classList.remove("hidden");
  ["skName", "skSource", "skTriggers", "skDo", "skDont"].forEach((id) => $(id).value = "");
  f.scrollIntoView({ behavior: "smooth", block: "start" });
}

async function saveSkill() {
  const body = {
    name: $("skName").value.trim(),
    source: $("skSource").value.trim() || null,
    triggers: $("skTriggers").value.split(/[，,]/).map((x) => x.trim()).filter(Boolean),
    do: $("skDo").value.trim(),
    dont: $("skDont").value.trim() || null,
  };
  if (!body.name || !body.do) { alert("技术名和「该怎么做」必填"); return; }
  await api("/skills", { method: "POST", body: JSON.stringify(body) });
  $("skillForm").classList.add("hidden");
  loadSkills();
}

async function importSkills() {
  let data;
  try {
    data = JSON.parse($("skImportText").value);
  } catch (e) {
    alert("JSON 解析失败：" + e.message);
    return;
  }
  if (!Array.isArray(data)) { alert("需要 JSON 数组"); return; }
  let ok = 0;
  for (const item of data) {
    try {
      await api("/skills", {
        method: "POST",
        body: JSON.stringify({
          name: item.name,
          source: item.source || null,
          triggers: item.triggers || [],
          do: item.do || "",
          dont: item.dont || null,
        }),
      });
      ok++;
    } catch (e) { /* 继续 */ }
  }
  $("skillImport").classList.add("hidden");
  $("skImportText").value = "";
  loadSkills();
  alert(`导入 ${ok}/${data.length} 张技术卡`);
}

async function init() {
  $("modelsBtn").onclick = () => refreshModels().catch((e) => ($("cfgStatus").textContent = e.message));
  $("saveCfgBtn").onclick = () => saveConfig().catch((e) => ($("cfgStatus").textContent = e.message));
  $("testCfgBtn").onclick = () => testConfig().catch((e) => ($("cfgStatus").textContent = e.message));
  $("cfgKeyShow").onclick = () => {
    $("cfgKey").type = $("cfgKey").type === "password" ? "text" : "password";
  };
  $("saveUserBtn").onclick = () => saveUser().catch((e) => alert(e.message));
  $("addPersonaBtn").onclick = () => buildForm(null);
  $("addSkillBtn").onclick = () => { $("skillImport").classList.add("hidden"); showSkillForm(); };
  $("importSkillBtn").onclick = () => { $("skillForm").classList.add("hidden"); $("skillImport").classList.remove("hidden"); };
  $("saveSkillBtn").onclick = () => saveSkill().catch((e) => alert("保存失败：" + e.message));
  $("cancelSkillBtn").onclick = () => $("skillForm").classList.add("hidden");
  $("doImportBtn").onclick = () => importSkills();

  loadConfig().catch((e) => ($("cfgStatus").textContent = e.message));
  loadUser().catch(() => {});
  loadPersonas().catch((e) => ($("personaList").textContent = "加载身份列表失败：" + e.message));
  loadSkills().catch((e) => ($("skillList").textContent = "加载技术卡失败：" + e.message));
}

init();
