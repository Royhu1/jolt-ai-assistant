/* ============================================================================
   JOLT 车队助手 — 前端逻辑（双语：默认 English，可切换中文）
   - 离线规则引擎：单车信息 / 两车能耗对比 / 车队概览 / 术语，纯本地零联网。
   - 在线 Claude 模式：检测到本地桥接服务时，把问题转发给 `claude -p`（走订阅）。
   - 多会话、历史记录（localStorage）、可点击示例问题、新建聊天、语言切换。
   ========================================================================== */
(function () {
  "use strict";

  const KB = window.FLEET_KB || { fleet: {}, fleet_aggregates: {}, glossary: {} };
  const FLEET = KB.fleet || {};
  const AGG = KB.fleet_aggregates || {};
  const REGS = Object.keys(FLEET);

  const LS_KEY = "jolt_chatbot_v1";
  const PREF_KEY = "jolt_chatbot_mode_pref"; // 'auto' | 'claude' | 'offline'
  const LANG_KEY = "jolt_chatbot_lang";      // 'en' | 'zh'
  const THEME_KEY = "jolt_chatbot_theme";    // 'light' | 'dark'
  const FS_KEY = "jolt_chatbot_fs";          // 内容字号缩放
  const FS_MIN = 0.85, FS_MAX = 1.6, FS_STEP = 0.1, FS_DEFAULT = 1.1;

  // ── 运行状态 ──────────────────────────────────────────────────────────────
  let bridgeOnline = false;
  let bridgeInfo = { auth_mode: null, model: null };
  let state = { chats: [], currentId: null };
  let modePref = localStorage.getItem(PREF_KEY) || "auto";
  let LANG = localStorage.getItem(LANG_KEY) || "en";   // 默认英文
  let THEME = localStorage.getItem(THEME_KEY) ||
    ((window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light");
  let FS = parseFloat(localStorage.getItem(FS_KEY)) || FS_DEFAULT;   // 默认偏大

  // ── DOM ───────────────────────────────────────────────────────────────────
  const $ = (s) => document.querySelector(s);
  const $$ = (s) => Array.from(document.querySelectorAll(s));
  const elChatScroll = $("#chatScroll");
  const elConvList = $("#convList");
  const elInput = $("#input");
  const elSend = $("#btnSend");
  const elChatTitle = $("#chatTitle");
  const elStatusDot = $("#statusDot");
  const elStatusText = $("#statusText");
  const elFleetMini = $("#fleetMini");
  const elComposerHint = $("#composerHint");
  const elModeClaude = $("#modeClaude");
  const elModeOffline = $("#modeOffline");
  const elSidebar = $("#sidebar");
  const elScrim = $("#scrim");
  const elThemeToggle = $("#themeToggle");
  const elThemeToggleText = $("#themeToggleText");

  // ── 工具函数 ──────────────────────────────────────────────────────────────
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function num(x, d) {
    if (x == null || isNaN(x)) return "—";
    const n = Number(x);
    return d == null ? String(n) : n.toFixed(d);
  }
  function intc(n) { return (n == null ? 0 : n).toLocaleString("en-US"); }
  function uid() { return "c" + Math.random().toString(36).slice(2, 9) + Date.now().toString(36).slice(-4); }
  function pct(a, b) { if (!a || !b) return null; return ((b - a) / a) * 100; }

  // ╔══════════════════════════════════════════════════════════════════════╗
  // ║  i18n — 翻译表（en / zh）                                               ║
  // ╚══════════════════════════════════════════════════════════════════════╝
  const TR = {
    en: {
      htmlLang: "en",
      appearance: "Appearance",
      themeToDark: "🌙 Dark", themeToLight: "☀️ Light",
      themeTitle: "Toggle light / dark theme",
      fontSmaller: "Smaller text", fontLarger: "Larger text",
      brandSub: "Electric HGV Fleet Assistant",
      newChat: "New chat",
      history: "History",
      newConversation: "New conversation",
      emptyChats: "No conversations yet",
      modeClaude: "Claude (sub)",
      modeOffline: "Offline rules",
      placeholder: "Ask anything… e.g. energy difference between YK73WFN and KY24LHT",
      statusChecking: "Checking…",
      statusOnline: (a) => `Bridge online · ${a}`,
      statusOffline: "Offline rules",
      authSubscription: "subscription",
      miniVehicles: "vehicles", miniMakes: "makes", miniTrips: "trips",
      claudeTitleOn: "Free-form Q&A via your Claude subscription",
      claudeTitleOff: "Start the local bridge first (see README)",
      hintClaude: (m) => `Enter to send · <b>⚡ Claude subscription</b>${m ? " (" + esc(m) + ")" : ""} · answered by your plan`,
      hintOfflineBridge: "Enter to send · <b>◐ Offline rules</b> (no quota) · switch to Claude for free-form questions",
      hintOfflineNoBridge: "Enter to send · <b>◐ Offline rules</b> · start the bridge to unlock Claude free-form Q&A",
      roleAssistant: "JOLT Assistant", roleMe: "Me",
      emptyReply: "(empty reply)",
      bridgeFail: (msg) => `⚠️ Bridge call failed (${esc(msg)}); fell back to offline rules:`,
      welcomeBadge: (v, m, t) => `⚡ ${v} vehicles · ${m} makes · ${intc(t)} trips`,
      welcomeHello: "Hello, I'm ",
      welcomeName: "the JOLT Fleet Assistant",
      welcomeDesc: "Ask me anything about this electric-HGV research project — a vehicle's specs and energy use, the difference between two vehicles, a fleet overview, or technical terms. Click an example to drop it into the input box.",
      examples: [
        { title: "Vehicle info", ico: "🚛", qs: ["Basic info on YK73WFN", "Detailed info on CMZ6260", "How far has AV24LXJ driven?"] },
        { title: "Compare", ico: "⚖️", qs: ["Energy difference between YK73WFN and KY24LHT", "Compare AV24LXJ and AV24LXK", "Volvo vs Scania — which is more efficient?"] },
        { title: "Fleet overview", ico: "📊", qs: ["What vehicles are in the fleet?", "Which vehicle is most efficient?", "Total distance across the fleet?"] },
        { title: "Terms", ico: "📖", qs: ["What does EP mean?", "What is driving cycle correction?", "What is regenerative braking?"] },
      ],
      bev: "Battery-electric HGV", diesel: "Diesel HGV",
      chipDiesel: (t) => `Diesel · <b>${num(t)} t</b> class`,
      chipNominal: (k) => `Nominal <b>${num(k)}</b> kWh`,
      chipUsable: (k) => `Usable <b>${num(k, 1)}</b> kWh`,
      chipTorque: (n) => `Peak torque <b>${num(n)}</b> N·m`,
      kAvgEP: "Average EP", kMedianEP: "Median EP", kTrips: "Trips", kDistance: "Total distance",
      kEPspread: "EP spread (±1σ)", kEPpctile: "EP 10–90 pctile", kAvgMass: "Avg GCVW", kAvgSpeed: "Avg speed",
      kAmbTemp: "Ambient temp", kMassRange: "GCVW range",
      cruiseVerdict: (c90, raw, n) => `🛣️ <b>Driving-cycle correction</b>: removing duty-cycle differences, the equivalent steady 90 km/h consumption is <b>EP@90 ≈ ${c90} kWh/km</b> (raw ${raw}, from ${intc(n)} trips). This is the fairer metric for cross-vehicle comparison.`,
      regNote: (r2, rmse) => `Regression fit (mass×elev etc.) R² = ${r2}, RMSE = ${rmse} kWh/km.`,
      weatherLabel: " Weather: ",
      basicVerdict: (mean, std, n, dist, reg) => `Average EP <b>${mean} kWh/km</b> (±${std}), over ${intc(n)} trips / ${dist} km. Ask "detailed info on ${esc(reg)}" for full stats.`,
      lowSample: (n) => `⚠️ Small sample (${n} trips); the mean may be unstable — treat as indicative.`,
      coverage: (a, b, n) => `📅 Data coverage: ${a} → ${b} (${n} periods).`,
      cmpTitle: "Energy comparison", cmpMetric: "Metric",
      rUsable: "Usable capacity (kWh)", rAvgEP: "Average EP (kWh/km)", rMedianEP: "Median EP",
      rAvgMass: "Avg GCVW (t)", rAvgSpeed: "Avg speed (km/h)", rDistance: "Total distance (km)", rTrips: "Trips",
      rCruise: "Cruise-corrected EP@90 (kWh/km)",
      cmpVerdict: (win, winEp, lose, loseEp, d) => `⚡ <b>${esc(win)}</b> is more efficient: average EP ${winEp} kWh/km, about <b>${d}%</b> lower than <b>${esc(lose)}</b>'s ${loseEp}.`,
      cmpTipBase: "Note: EP depends on payload, speed, terrain and temperature; different duty cycles mean this isn't a pure vehicle difference. ",
      cmpTipCruise: "The 'Cruise-corrected EP@90' row above removes duty-cycle differences for a fairer comparison.",
      cmpTipNoCruise: "For a fairer basis, use cruise-corrected EP@90 (not available for all vehicles).",
      cmpLowNote: " (Note: one of them has a small sample, so treat the conclusion as indicative.)",
      cmpMissingDiesel: (m) => `⚠️ <b>${esc(m)}</b> is a diesel vehicle (consumption in L/100km), so a direct kWh/km comparison isn't possible. You can still compare specs (capacity, weight class, etc.).`,
      cmpMissingNoData: (m) => `⚠️ <b>${esc(m)}</b> has no per-trip energy stats yet, so a direct kWh/km comparison isn't possible. You can still compare specs (capacity, weight class, etc.).`,
      ovTitle: "Fleet overview", ovVehicles: "Vehicles", ovEvDiesel: "BEV / Diesel", ovMakes: "Makes",
      ovTripsAnalysed: "Trips analysed", ovDistance: "Total distance", ovMakesLine: (m) => `Makes: ${esc(m)}`,
      thReg: "Reg", thModel: "Model", thUsable: "Usable kWh", thAvgEP: "Avg EP", thTrips: "Trips",
      tDiesel: "Diesel",
      ovVerdict: (me, meEp, le, leEp, n) => `Most efficient <b>${esc(me)}</b> (${meEp} kWh/km) · least efficient <b>${esc(le)}</b> (${leEp} kWh/km). <span class="note" style="display:block;margin-top:4px">Ranking includes only vehicles with ≥${n} trips.</span>`,
      rankThRank: "Rank",
      rankTitleMake: (m) => `${esc(m)} efficiency ranking`,
      rankTitleFleet: "Fleet efficiency ranking",
      rankVerdict: (best, bestEp, worst, worstEp, multi) => `⚡ Most efficient <b>${esc(best)}</b> (${bestEp} kWh/km)` + (multi ? `, least <b>${esc(worst)}</b> (${worstEp})` : "") + ".",
      rankNoData: (m) => `<p>No energy stats for ${esc(m)} vehicles yet.</p>`,
      mkTitle: "Make comparison", mkMake: "Make", mkCount: "# vehicles", mkAvgEP: "Trip-weighted avg EP", mkSample: "Sample trips",
      mkVerdict: (mk, ep) => `⚡ <b>${esc(mk)}</b> has the lowest trip-weighted average EP (${ep} kWh/km). <span class="note" style="display:block;margin-top:4px">Note: makes differ in vehicle count / duty cycle; macro view only.</span>`,
      greeting: () => `<div class="veh-card">
        <p>Hi! I'm the <b>JOLT Fleet Assistant</b> ⚡, here to answer questions about this electric-HGV research project. The knowledge base currently covers
        <b>${AGG.n_vehicles}</b> vehicles (${AGG.n_ev} BEV + ${AGG.n_diesel} diesel, ${AGG.n_makes} makes), with
        <b>${intc(AGG.total_trips_analysed)}</b> trips analysed over ~<b>${num(AGG.total_distance_km, 0)}</b> km.</p>
        <p>You can ask me about:</p>
        <ul>
          <li>A vehicle's <b>basic / detailed info</b> — e.g. "detailed info on YK73WFN"</li>
          <li>The <b>energy difference</b> between two vehicles — e.g. "YK73WFN vs KY24LHT"</li>
          <li>A <b>fleet overview</b> / which is most efficient — e.g. "which vehicle is most efficient?"</li>
          <li><b>Term definitions</b> — e.g. "what does EP mean?"</li>
        </ul>
        <p class="note">This is offline rule mode (no network, no quota). Start the local bridge and switch to "Claude subscription" mode for free-form questions.</p>
      </div>`,
      fallback: () => `<div class="veh-card">
        <p>🤔 The offline rule engine didn't quite get that. I'm good at:</p>
        <ul>
          <li>Info on a vehicle (e.g. <code>YK73WFN</code>, <code>CMZ6260</code>)</li>
          <li>Two-vehicle energy comparison (e.g. "AV24LXJ and AV24LXK")</li>
          <li>Fleet overview / most efficient / make comparison</li>
          <li>Terms (EP, SOC, regen braking, cruise correction…)</li>
        </ul>
        <p class="note">Want free-form questions? Start the bridge (see README) and switch the top-right toggle to "⚡ Claude subscription" so Claude answers on your plan.</p>
      </div>`,
      glossaryTitle: (k) => `📖 ${esc(k)}`,
    },

    zh: {
      htmlLang: "zh-CN",
      appearance: "外观",
      themeToDark: "🌙 暗色", themeToLight: "☀️ 亮色",
      themeTitle: "切换 亮色 / 暗色 主题",
      fontSmaller: "更小字号", fontLarger: "更大字号",
      brandSub: "Electric HGV Fleet Assistant",
      newChat: "新建聊天",
      history: "历史对话",
      newConversation: "新的对话",
      emptyChats: "还没有对话",
      modeClaude: "Claude 订阅",
      modeOffline: "离线规则",
      placeholder: "问点什么…例如：YK73WFN 和 KY24LHT 的能耗差异",
      statusChecking: "检测中…",
      statusOnline: (a) => `桥接在线 · ${a}`,
      statusOffline: "离线规则模式",
      authSubscription: "订阅",
      miniVehicles: "辆车", miniMakes: "厂商", miniTrips: "行程",
      claudeTitleOn: "用 Claude 订阅自由问答",
      claudeTitleOff: "需先启动本地桥接服务（见 README）",
      hintClaude: (m) => `Enter 发送 · <b>⚡ Claude 订阅模式</b>${m ? "（" + esc(m) + "）" : ""} · 由你的订阅作答`,
      hintOfflineBridge: "Enter 发送 · <b>◐ 离线规则模式</b>（零额度）· 切到 Claude 可自由提问",
      hintOfflineNoBridge: "Enter 发送 · <b>◐ 离线规则模式</b> · 启动桥接服务可解锁 Claude 自由问答",
      roleAssistant: "JOLT 助手", roleMe: "我",
      emptyReply: "（空回复）",
      bridgeFail: (msg) => `⚠️ 桥接服务调用失败（${esc(msg)}），已回退离线规则：`,
      welcomeBadge: (v, m, t) => `⚡ ${v} 辆车 · ${m} 个厂商 · ${intc(t)} 行程`,
      welcomeHello: "你好，我是 ",
      welcomeName: "JOLT 车队助手",
      welcomeDesc: "问我任何关于这个电动重卡研究项目的问题 —— 某辆车的规格与能耗、两辆车之间的差异、整个车队的概览，或者专业术语。点下面的示例直接填入输入框。",
      examples: [
        { title: "单车信息", ico: "🚛", qs: ["YK73WFN 的基本信息", "详细介绍一下 CMZ6260", "AV24LXJ 一共跑了多少公里？"] },
        { title: "两车 / 厂商对比", ico: "⚖️", qs: ["YK73WFN 和 KY24LHT 的能耗差异", "对比 AV24LXJ 和 AV24LXK", "Volvo 和 Scania 哪个更省电？"] },
        { title: "车队概览", ico: "📊", qs: ["车队里都有哪些车？", "哪辆车最省电、哪辆最费电？", "整个车队总共跑了多少里程？"] },
        { title: "概念 / 术语", ico: "📖", qs: ["EP（能耗）是什么意思？", "什么是巡航工况修正？", "再生制动的回收效率有多高？"] },
      ],
      bev: "纯电动 HGV", diesel: "柴油 HGV",
      chipDiesel: (t) => `柴油 · <b>${num(t)} t</b> 级`,
      chipNominal: (k) => `标称 <b>${num(k)}</b> kWh`,
      chipUsable: (k) => `有效容量 <b>${num(k, 1)}</b> kWh`,
      chipTorque: (n) => `峰值扭矩 <b>${num(n)}</b> N·m`,
      kAvgEP: "平均能耗 EP", kMedianEP: "EP 中位数", kTrips: "行程数", kDistance: "累计里程",
      kEPspread: "EP 波动 (±1σ)", kEPpctile: "EP 10–90 分位", kAvgMass: "平均车重 GCVW", kAvgSpeed: "平均速度",
      kAmbTemp: "环境温度", kMassRange: "车重范围",
      cruiseVerdict: (c90, raw, n) => `🛣️ <b>巡航工况修正</b>：把驾驶工况差异消除后，等效 90 km/h 稳态能耗 <b>EP@90 ≈ ${c90} kWh/km</b>（原始 ${raw}，基于 ${intc(n)} 行程）。这是跨车公平对比时更应使用的指标。`,
      regNote: (r2, rmse) => `回归拟合（mass×elev 等因素）R² = ${r2}，RMSE = ${rmse} kWh/km。`,
      weatherLabel: " 天气分布：",
      basicVerdict: (mean, std, n, dist, reg) => `平均能耗 <b>${mean} kWh/km</b>（±${std}），覆盖 ${intc(n)} 行程、${dist} km。想看完整统计可问「${esc(reg)} 的详细信息」。`,
      lowSample: (n) => `⚠️ 该车样本量较小（${n} 行程），均值可能不够稳定，仅供参考。`,
      coverage: (a, b, n) => `📅 数据覆盖：${a} → ${b}（${n} 个统计周期）。`,
      cmpTitle: "能耗对比", cmpMetric: "指标",
      rUsable: "有效容量 (kWh)", rAvgEP: "平均能耗 EP (kWh/km)", rMedianEP: "EP 中位数",
      rAvgMass: "平均车重 GCVW (t)", rAvgSpeed: "平均速度 (km/h)", rDistance: "累计里程 (km)", rTrips: "行程数",
      rCruise: "巡航修正 EP@90 (kWh/km)",
      cmpVerdict: (win, winEp, lose, loseEp, d) => `⚡ <b>${esc(win)}</b> 更省电：平均能耗 ${winEp} kWh/km，比 <b>${esc(lose)}</b> 的 ${loseEp} 低约 <b>${d}%</b>。`,
      cmpTipBase: "提示：EP 受载重、速度、路况、温度影响，两车工况不同则非纯车辆差异。",
      cmpTipCruise: "上表「巡航修正 EP@90」已消除工况差异，对比更公平。",
      cmpTipNoCruise: "如需更公平的口径，建议用巡航修正 EP@90（部分车暂无）。",
      cmpLowNote: "（注意其中有车样本量较小，结论仅供参考。）",
      cmpMissingDiesel: (m) => `⚠️ <b>${esc(m)}</b> 为柴油车，能耗以 L/100km 计量，无法直接做 kWh/km 对比。可对比规格（容量、车重级别等）。`,
      cmpMissingNoData: (m) => `⚠️ <b>${esc(m)}</b> 暂无 per-trip 能耗统计，无法直接做 kWh/km 对比。可对比规格（容量、车重级别等）。`,
      ovTitle: "车队概览", ovVehicles: "车辆总数", ovEvDiesel: "纯电 / 柴油", ovMakes: "厂商",
      ovTripsAnalysed: "已分析行程", ovDistance: "累计里程", ovMakesLine: (m) => `厂商：${esc(m)}`,
      thReg: "车牌", thModel: "车型", thUsable: "有效容量", thAvgEP: "平均 EP", thTrips: "行程",
      tDiesel: "柴油",
      ovVerdict: (me, meEp, le, leEp, n) => `最省电 <b>${esc(me)}</b>（${meEp} kWh/km）· 最费电 <b>${esc(le)}</b>（${leEp} kWh/km）。<span class="note" style="display:block;margin-top:4px">排名仅纳入 ≥${n} 行程的车。</span>`,
      rankThRank: "排名",
      rankTitleMake: (m) => `${esc(m)} 车型能耗排名`,
      rankTitleFleet: "全车队能耗排名",
      rankVerdict: (best, bestEp, worst, worstEp, multi) => `⚡ 最省 <b>${esc(best)}</b>（${bestEp} kWh/km）` + (multi ? `，最费 <b>${esc(worst)}</b>（${worstEp}）` : "") + "。",
      rankNoData: (m) => `<p>暂无 ${esc(m)} 车型的能耗统计数据。</p>`,
      mkTitle: "厂商能耗对比", mkMake: "厂商", mkCount: "车数", mkAvgEP: "行程加权平均 EP", mkSample: "样本行程",
      mkVerdict: (mk, ep) => `⚡ <b>${esc(mk)}</b> 行程加权平均能耗最低（${ep} kWh/km）。<span class="note" style="display:block;margin-top:4px">注：各厂商车型数 / 工况不同，仅供宏观参考。</span>`,
      greeting: () => `<div class="veh-card">
        <p>你好！我是 <b>JOLT 车队助手</b> ⚡，专门回答这个电动重卡研究项目的问题。当前知识库覆盖
        <b>${AGG.n_vehicles}</b> 辆车（${AGG.n_ev} 纯电 + ${AGG.n_diesel} 柴油，${AGG.n_makes} 个厂商），
        累计分析 <b>${intc(AGG.total_trips_analysed)}</b> 个行程、约 <b>${num(AGG.total_distance_km, 0)}</b> km。</p>
        <p>你可以问我：</p>
        <ul>
          <li>某辆车的<b>基本/详细信息</b> —— 例：「YK73WFN 的详细信息」</li>
          <li>两辆车的<b>能耗差异</b> —— 例：「YK73WFN 和 KY24LHT 的能耗对比」</li>
          <li><b>车队概览</b> / 谁最省电 —— 例：「哪辆车最省电？」</li>
          <li><b>术语解释</b> —— 例：「EP 是什么意思？」</li>
        </ul>
        <p class="note">当前为离线规则模式（零联网、零额度）。启动本地桥接服务后切到「Claude 订阅」模式，即可自由提任意问题。</p>
      </div>`,
      fallback: () => `<div class="veh-card">
        <p>🤔 离线规则模式没太理解这个问题。我擅长这几类：</p>
        <ul>
          <li>某辆车的信息（如 <code>YK73WFN</code>、<code>CMZ6260</code>）</li>
          <li>两车能耗对比（如「AV24LXJ 和 AV24LXK」）</li>
          <li>车队概览 / 最省电 / 厂商对比</li>
          <li>术语（EP、SOC、再生制动、巡航修正…）</li>
        </ul>
        <p class="note">想自由提问？启动桥接服务（见 README）后，把右上角切到「⚡ Claude 订阅」模式即可由 Claude 用订阅作答。</p>
      </div>`,
      glossaryTitle: (k) => `📖 ${esc(k)}`,
    },
  };
  const S = () => TR[LANG];

  // 术语表（双语；离线卡片用，键与 GLOSSARY_ALIASES 一致）
  const GLOSSARY_TR = {
    "EP (Energy Performance)": {
      en: "Energy intensity in kWh/km, = |ΔE_total| / distance driven. In the xlsx it's net EP (regen already deducted). Lower is more efficient.",
      zh: "能耗强度，单位 kWh/km，= |ΔE_total| / 行驶距离。xlsx 中为 net EP（已扣除再生回收）。越低越省电。",
    },
    "EP_gross": {
      en: "Consumption with regen added back: (|ΔE_total| + E_recup) / distance.",
      zh: "把再生回收能量加回去的能耗：(|ΔE_total| + E_recup) / 距离。",
    },
    "EP_cruise@90": {
      en: "The vehicle's telematics EP projected — via driving-cycle correction — to an equivalent steady 90 km/h cruise, for fair cross-vehicle comparison.",
      zh: "把整车 telematics EP 经驾驶工况修正投射到 90 km/h 稳态巡航的等效能耗，用于跨车公平对比。",
    },
    "SOC": { en: "State of Charge — the battery charge level (%).", zh: "State of Charge，电池荷电状态（%）。" },
    "Effective capacity": {
      en: "Corrected usable battery capacity (kWh); can differ from nominal / SRF capacity.",
      zh: "经修正的有效电池容量（kWh），可与标称 / SRF 容量不同。",
    },
    "Regen / Recuperation": {
      en: "Regenerative braking energy recovery. YK73WFN's system-level η_regen ≈ 0.42.",
      zh: "再生制动回收能量。YK73WFN 系统级 η_regen ≈ 0.42。",
    },
    "GCVW": {
      en: "Gross Combination Vehicle Weight (tractor + trailer + payload), in tonnes.",
      zh: "Gross Combination Vehicle Weight，总组合车重（含挂车与载荷），单位 t。",
    },
    "Driving cycle correction": {
      en: "Removing speed-profile differences (Case 1/2/3) before comparing cruise consumption.",
      zh: "驾驶工况修正（Case 1/2/3），消除速度剖面差异后比较巡航能耗。",
    },
    "Crr / CdA": {
      en: "Rolling-resistance coefficient / drag area — parameter-identification quantities.",
      zh: "滚动阻力系数 / 风阻面积，参数辨识专题量。",
    },
    "Diesel fuel consumption": {
      en: "Diesel consumption is measured in L/100km; diesel LHV defaults to 10 kWh/L.",
      zh: "柴油车能耗以 L/100km 计量；柴油 LHV 默认 10 kWh/L。",
    },
  };

  // ╔══════════════════════════════════════════════════════════════════════╗
  // ║  极简 Markdown 渲染（自包含，无外部依赖）                                ║
  // ╚══════════════════════════════════════════════════════════════════════╝
  function renderMarkdown(src) {
    src = String(src || "").replace(/\r\n/g, "\n");
    const codeBlocks = [];
    src = src.replace(/```(\w*)\n?([\s\S]*?)```/g, (_, lang, code) => {
      const i = codeBlocks.length;
      codeBlocks.push("<pre><code>" + esc(code.replace(/\n$/, "")) + "</code></pre>");
      return "\n@@JOLTCB" + i + "@@\n";
    });

    const isTableSep = (ln) =>
      ln != null && ln.includes("|") && ln.includes("-") &&
      /^\s*\|?[\s:|-]+\|?\s*$/.test(ln);

    const lines = src.split("\n");
    let html = "";
    let i = 0;
    const inline = (t) => {
      t = esc(t);
      t = t.replace(/`([^`]+)`/g, (_, c) => "<code>" + c + "</code>");
      t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
      t = t.replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
      t = t.replace(/\[([^\]]+)\]\((https?:[^)]+)\)/g,
        '<a href="$2" target="_blank" rel="noopener">$1</a>');
      t = t.replace(/@@JOLTCB(\d+)@@/g, (_, n) => codeBlocks[+n] || "");
      return t;
    };

    while (i < lines.length) {
      const line = lines[i];
      const cb = line.trim().match(/^@@JOLTCB(\d+)@@$/);
      if (cb) { html += codeBlocks[+cb[1]] || ""; i++; continue; }
      if (/^\s*$/.test(line)) { i++; continue; }

      if (line.includes("|") && isTableSep(lines[i + 1])) {
        const head = line.split("|").filter((c) => c.trim() !== "");
        i += 2;
        let rows = "";
        while (i < lines.length && lines[i].includes("|") && lines[i].trim() !== "") {
          const cells = lines[i].split("|").filter((c, idx, arr) =>
            !(idx === 0 && c.trim() === "") && !(idx === arr.length - 1 && c.trim() === ""));
          rows += "<tr>" + cells.map((c) => "<td>" + inline(c.trim()) + "</td>").join("") + "</tr>";
          i++;
        }
        html += "<table><thead><tr>" + head.map((h) => "<th>" + inline(h.trim()) + "</th>").join("") +
                "</tr></thead><tbody>" + rows + "</tbody></table>";
        continue;
      }

      const h = line.match(/^(#{1,3})\s+(.*)$/);
      if (h) { const lv = h[1].length; html += "<h" + lv + ">" + inline(h[2]) + "</h" + lv + ">"; i++; continue; }

      if (/^\s*[-*+]\s+/.test(line)) {
        let items = "";
        while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) {
          items += "<li>" + inline(lines[i].replace(/^\s*[-*+]\s+/, "")) + "</li>"; i++;
        }
        html += "<ul>" + items + "</ul>"; continue;
      }
      if (/^\s*\d+\.\s+/.test(line)) {
        let items = "";
        while (i < lines.length && /^\s*\d+\.\s+/.test(lines[i])) {
          items += "<li>" + inline(lines[i].replace(/^\s*\d+\.\s+/, "")) + "</li>"; i++;
        }
        html += "<ol>" + items + "</ol>"; continue;
      }
      if (/^\s*>\s?/.test(line)) {
        const buf = [];
        while (i < lines.length && /^\s*>\s?/.test(lines[i])) { buf.push(lines[i].replace(/^\s*>\s?/, "")); i++; }
        html += "<blockquote>" + inline(buf.join(" ")) + "</blockquote>"; continue;
      }

      const buf = [line]; i++;
      while (i < lines.length && !/^\s*$/.test(lines[i]) &&
             !/^(#{1,3}\s|\s*[-*+]\s|\s*\d+\.\s|\s*>|@@JOLTCB)/.test(lines[i]) &&
             !(lines[i].includes("|") && isTableSep(lines[i + 1]))) {
        buf.push(lines[i]); i++;
      }
      html += "<p>" + inline(buf.join(" ")) + "</p>";
    }
    return html;
  }

  // ╔══════════════════════════════════════════════════════════════════════╗
  // ║  规则引擎 —— 离线问答                                                   ║
  // ╚══════════════════════════════════════════════════════════════════════╝
  const MAKE_ALIASES = {
    Volvo: ["volvo", "沃尔沃"],
    Scania: ["scania", "斯堪尼亚"],
    Renault: ["renault", "雷诺"],
    "Mercedes-Benz": ["mercedes", "benz", "奔驰", "mercedes-benz", "eactros"],
    DAF: ["daf", "达夫"],
  };
  const GLOSSARY_ALIASES = {
    "EP (Energy Performance)": ["energy performance", "能耗强度", "ep是", "什么是ep", "ep "],
    "EP_gross": ["ep_gross", "gross ep", "毛能耗", "含再生回收的能耗"],
    "EP_cruise@90": ["cruise", "巡航", "ep_cruise", "工况修正后", "90km/h"],
    "SOC": ["soc", "荷电", "电量状态"],
    "Effective capacity": ["有效容量", "effective capacity", "effective_capacity"],
    "Regen / Recuperation": ["regen", "再生", "回收", "recup", "recuperation", "制动回收"],
    "GCVW": ["gcvw", "总重", "组合车重", "gross combination"],
    "Driving cycle correction": ["工况修正", "driving cycle", "driving-cycle", "case 1", "case 2", "case 3", "驾驶工况"],
    "Crr / CdA": ["crr", "cda", "滚阻", "风阻", "滚动阻力", "风阻面积"],
    "Diesel fuel consumption": ["柴油", "diesel", "l/100km", "油耗"],
  };

  function findRegs(text) {
    const compact = text.toUpperCase().replace(/\s+/g, "");
    const hits = [];
    for (const reg of REGS) {
      const idx = compact.indexOf(reg);
      if (idx >= 0) hits.push({ reg, idx });
    }
    hits.sort((a, b) => a.idx - b.idx);
    const seen = new Set(); const out = [];
    for (const h of hits) if (!seen.has(h.reg)) { seen.add(h.reg); out.push(h.reg); }
    return out;
  }
  function findMakes(text) {
    const low = text.toLowerCase();
    const out = [];
    for (const [make, al] of Object.entries(MAKE_ALIASES)) {
      if (al.some((a) => low.includes(a))) out.push(make);
    }
    return out;
  }
  function hasAny(text, arr) { const l = text.toLowerCase(); return arr.some((k) => l.includes(k)); }

  const isCompare = (q) => hasAny(q, ["对比", "比较", "差异", "差别", "区别", "vs", "versus", "compare", "difference", "哪个更", "哪辆更"]);
  const isOverview = (q) => hasAny(q, ["车队", "所有车", "有哪些", "多少辆", "列表", "清单", "概览", "总览", "fleet", "overview", "list", "总里程", "总共", "整个", "all vehicles", "total distance"]);
  const isMostLeast = (q) => hasAny(q, ["最省", "最费", "最高效", "最低效", "最节能", "最耗", "most efficient", "least efficient", "排名", "排行", "谁最", "哪辆最", "哪个最", "ranking", "rank"]);
  const isGreeting = (q) => hasAny(q, ["你好", "您好", "hi", "hello", "帮助", "help", "你能", "怎么用", "能做什么", "使用说明", "介绍一下你", "你是谁", "who are you", "what can you"]);
  const wantsDetail = (q) => hasAny(q, ["详细", "详情", "具体", "全部", "完整", "detail", "深入", "更多", "所有信息", "full stats"]);

  function findGlossary(q) {
    const low = q.toLowerCase();
    const cue = hasAny(q, ["什么是", "是什么", "什么意思", "定义", "含义", "意思", "解释", "what is", "what does", "explain", "怎么算", "如何计算", "啥意思", "mean", "means", "stand for", "definition"]);
    let best = null, bestPos = Infinity;
    for (const [key, al] of Object.entries(GLOSSARY_ALIASES)) {
      for (const a of al) {
        const p = low.indexOf(a.trim());
        if (p >= 0 && p < bestPos) { best = key; bestPos = p; }
      }
    }
    if (best && (cue || low.trim().length <= 14)) return best;
    return null;
  }

  // —— 富卡片构建 ——
  function specChips(s) {
    const L = S();
    const c = [];
    c.push(`<span class="chip"><b>${esc(s.make)}</b> ${esc(s.model)}</span>`);
    if (s.is_diesel) {
      c.push(`<span class="chip">${L.chipDiesel(s.weight_class_t)}</span>`);
    } else {
      if (s.nominal_kwh) c.push(`<span class="chip">${L.chipNominal(s.nominal_kwh)}</span>`);
      if (s.effective_capacity_kwh) c.push(`<span class="chip">${L.chipUsable(s.effective_capacity_kwh)}</span>`);
      if (s.max_torque_nm) c.push(`<span class="chip">${L.chipTorque(s.max_torque_nm)}</span>`);
    }
    return `<div class="chip-row">${c.join("")}</div>`;
  }

  function statBox(k, v, unit, small) {
    return `<div class="stat"><div class="k">${k}</div><div class="v${small ? " sm" : ""}">${v}${unit ? ` <small>${unit}</small>` : ""}</div></div>`;
  }

  function vehicleCard(reg, detailed) {
    const L = S();
    const r = FLEET[reg]; const s = r.spec;
    let h = `<div class="veh-card"><div class="veh-head">
      <span class="veh-badge">${esc(s.srf_reg)}</span>
      <span class="veh-name">${esc(s.make)} ${esc(s.model)}<small>${s.is_diesel ? L.diesel : L.bev}</small></span>
    </div>`;
    h += specChips(s);

    if (r.energy_available && r.trips) {
      const t = r.trips, ep = t.ep_kwh_per_km;
      h += `<div class="stat-grid">
        ${statBox(L.kAvgEP, num(ep.mean, 3), "kWh/km")}
        ${statBox(L.kMedianEP, num(ep.median, 3), "kWh/km")}
        ${statBox(L.kTrips, intc(t.n_trips), "")}
        ${statBox(L.kDistance, num(t.total_distance_km, 0), "km")}
      </div>`;
      if (detailed) {
        h += `<div class="stat-grid">
          ${statBox(L.kEPspread, "±" + num(ep.std, 3), "")}
          ${statBox(L.kEPpctile, num(ep.p10, 2) + "–" + num(ep.p90, 2), "", true)}
          ${statBox(L.kAvgMass, num(t.mass_t.mean, 1), "t")}
          ${statBox(L.kAvgSpeed, num(t.speed_kmh_mean, 1), "km/h")}
          ${statBox(L.kAmbTemp, num(t.t_amb_c.min, 0) + "–" + num(t.t_amb_c.max, 0), "°C", true)}
          ${statBox(L.kMassRange, num(t.mass_t.min, 0) + "–" + num(t.mass_t.max, 0), "t", true)}
        </div>`;
        if (r.cruise_correction) {
          const cc = r.cruise_correction;
          h += `<div class="verdict">${L.cruiseVerdict(num(cc.ep_cruise90_mean, 3), num(cc.ep_raw_mean, 3), cc.n_trips)}</div>`;
        }
        if (r.regression) {
          h += `<p class="note">${L.regNote(num(r.regression.r2, 2), num(r.regression.rmse, 3))}`;
          if (t.weather_counts) {
            const w = Object.entries(t.weather_counts).map(([k, v]) => `${k} ${v}`).join(" · ");
            h += `${L.weatherLabel}${esc(w)}${LANG === "en" ? "." : "。"}`;
          }
          h += `</p>`;
        }
      } else {
        h += `<div class="verdict">${L.basicVerdict(num(ep.mean, 3), num(ep.std, 3), t.n_trips, num(t.total_distance_km, 0), reg)}</div>`;
      }
      if (t.low_sample) h += `<p class="note">${L.lowSample(t.n_trips)}</p>`;
    } else if (r.energy_note) {
      // energy_note 仅有中文；英文模式下给一个等价英文说明
      const note = (LANG === "en" && s.is_diesel)
        ? "Diesel vehicle — consumption is measured in L/100km (not kWh/km); not part of the BEV EP stats. See reports/2.2.2/WU70GLV/."
        : (LANG === "en")
          ? "Not yet included in per-trip energy aggregation (insufficient data or recently onboarded); only specs and data coverage are available."
          : r.energy_note;
      h += `<div class="verdict">${esc(note)}</div>`;
    }

    if (r.coverage) h += `<p class="note">${L.coverage(r.coverage.date_start, r.coverage.date_end, r.coverage.n_periods)}</p>`;
    h += `</div>`;
    return h;
  }

  function compareVehicles(a, b) {
    const L = S();
    const ra = FLEET[a], rb = FLEET[b];
    const sa = ra.spec, sb = rb.spec;
    const epa = ra.trips?.ep_kwh_per_km?.mean, epb = rb.trips?.ep_kwh_per_km?.mean;

    const row = (label, va, vb, better, na, nb) => {
      let ca = "", cb = "";
      const hasN = na != null && nb != null && !isNaN(na) && !isNaN(nb);
      if (better && hasN && na !== nb) {
        const aWins = better === "low" ? na < nb : na > nb;
        ca = aWins ? "winner" : "loser"; cb = aWins ? "loser" : "winner";
      }
      return `<tr><td>${esc(label)}</td><td class="num ${ca}">${va}</td><td class="num ${cb}">${vb}</td></tr>`;
    };

    const meda = ra.trips?.ep_kwh_per_km?.median, medb = rb.trips?.ep_kwh_per_km?.median;
    let h = `<div class="veh-card"><div class="veh-head"><span class="veh-name">${L.cmpTitle}</span></div>
      <table class="jolt"><thead><tr><th>${L.cmpMetric}</th>
        <th>${esc(a)}<br><small style="font-weight:400;color:#94a3b8">${esc(sa.make)} ${esc(sa.model)}</small></th>
        <th>${esc(b)}<br><small style="font-weight:400;color:#94a3b8">${esc(sb.make)} ${esc(sb.model)}</small></th>
      </tr></thead><tbody>`;
    h += row(L.rUsable, num(sa.effective_capacity_kwh, 1), num(sb.effective_capacity_kwh, 1), null);
    h += row(L.rAvgEP, num(epa, 3), num(epb, 3), "low", epa, epb);
    h += row(L.rMedianEP, num(meda, 3), num(medb, 3), "low", meda, medb);
    h += row(L.rAvgMass, num(ra.trips?.mass_t?.mean, 1), num(rb.trips?.mass_t?.mean, 1), null);
    h += row(L.rAvgSpeed, num(ra.trips?.speed_kmh_mean, 1), num(rb.trips?.speed_kmh_mean, 1), null);
    h += row(L.rDistance, num(ra.trips?.total_distance_km, 0), num(rb.trips?.total_distance_km, 0), null);
    h += row(L.rTrips, ra.trips ? intc(ra.trips.n_trips) : "—", rb.trips ? intc(rb.trips.n_trips) : "—", null);
    const c90a = ra.cruise_correction?.ep_cruise90_mean, c90b = rb.cruise_correction?.ep_cruise90_mean;
    if (c90a != null && c90b != null) h += row(L.rCruise, num(c90a, 3), num(c90b, 3), "low", c90a, c90b);
    h += `</tbody></table>`;

    if (epa != null && epb != null) {
      const d = pct(Math.min(epa, epb), Math.max(epa, epb));
      const win = epa < epb ? a : b, lose = epa < epb ? b : a;
      h += `<div class="verdict">${L.cmpVerdict(win, num(Math.min(epa, epb), 3), lose, num(Math.max(epa, epb), 3), num(d, 1))}</div>`;
      const lowNote = (ra.trips?.low_sample || rb.trips?.low_sample) ? L.cmpLowNote : "";
      const cruiseNote = (c90a != null && c90b != null) ? L.cmpTipCruise : L.cmpTipNoCruise;
      h += `<p class="note">${L.cmpTipBase}${cruiseNote}${lowNote}</p>`;
    } else {
      const missing = epa == null ? a : b;
      h += `<div class="verdict">${FLEET[missing].spec.is_diesel ? L.cmpMissingDiesel(missing) : L.cmpMissingNoData(missing)}</div>`;
    }
    h += `</div>`;
    return h;
  }

  function fleetOverview() {
    const L = S(); const a = AGG;
    let h = `<div class="veh-card">
      <div class="veh-head"><span class="veh-name">${L.ovTitle}</span></div>
      <div class="stat-grid">
        ${statBox(L.ovVehicles, a.n_vehicles, "")}
        ${statBox(L.ovEvDiesel, a.n_ev, "/ " + a.n_diesel)}
        ${statBox(L.ovMakes, a.n_makes, "")}
        ${statBox(L.ovTripsAnalysed, intc(a.total_trips_analysed), "")}
        ${statBox(L.ovDistance, num(a.total_distance_km, 0), "km")}
      </div>
      <p class="note">${L.ovMakesLine((a.makes || []).join(" · "))}</p>`;

    const rows = REGS.map((reg) => {
      const r = FLEET[reg], s = r.spec;
      return { reg, make: s.make, model: s.model, diesel: s.is_diesel, cap: s.effective_capacity_kwh, ep: r.trips?.ep_kwh_per_km?.mean, n: r.trips?.n_trips };
    });
    rows.sort((x, y) => { if (x.ep == null) return 1; if (y.ep == null) return -1; return x.ep - y.ep; });
    h += `<table class="jolt"><thead><tr><th>${L.thReg}</th><th>${L.thModel}</th><th>${L.thUsable}</th><th>${L.thAvgEP}</th><th>${L.thTrips}</th></tr></thead><tbody>`;
    for (const x of rows) {
      const epTxt = x.diesel ? `<span style='color:#94a3b8'>${L.tDiesel}</span>` : (x.ep != null ? num(x.ep, 3) : "—");
      h += `<tr><td><b>${esc(x.reg)}</b></td><td>${esc(x.make)} ${esc(x.model)}</td>
        <td class="num">${x.cap ? num(x.cap, 0) : "—"}</td><td class="num">${epTxt}</td>
        <td class="num">${x.n ? intc(x.n) : "—"}</td></tr>`;
    }
    h += `</tbody></table>`;
    const mr = a.ep_kwh_per_km_fleet_range || {};
    if (mr.most_efficient && mr.least_efficient) {
      h += `<div class="verdict">${L.ovVerdict(mr.most_efficient.reg, num(mr.most_efficient.ep, 3), mr.least_efficient.reg, num(mr.least_efficient.ep, 3), mr.ranking_min_trips)}</div>`;
    }
    h += `</div>`;
    return h;
  }

  function rankedList(regs, title) {
    const L = S();
    const arr = regs.map((reg) => ({ reg, r: FLEET[reg], ep: FLEET[reg].trips?.ep_kwh_per_km?.mean, n: FLEET[reg].trips?.n_trips }))
      .filter((x) => x.ep != null);
    arr.sort((a, b) => a.ep - b.ep);
    if (!arr.length) return null;
    let h = `<div class="veh-card"><div class="veh-head"><span class="veh-name">${esc(title)}</span></div>
      <table class="jolt"><thead><tr><th>${L.rankThRank}</th><th>${L.thReg}</th><th>${L.thModel}</th><th>${L.thAvgEP}</th><th>${L.thTrips}</th></tr></thead><tbody>`;
    arr.forEach((x, i) => {
      const cls = i === 0 ? "winner" : (i === arr.length - 1 ? "loser" : "");
      h += `<tr><td>${i + 1}</td><td class="${cls}"><b>${esc(x.reg)}</b></td>
        <td>${esc(x.r.spec.make)} ${esc(x.r.spec.model)}</td>
        <td class="num ${cls}">${num(x.ep, 3)}</td><td class="num">${intc(x.n)}</td></tr>`;
    });
    h += `</tbody></table>`;
    const best = arr[0], worst = arr[arr.length - 1];
    h += `<div class="verdict">${L.rankVerdict(best.reg, num(best.ep, 3), worst.reg, num(worst.ep, 3), arr.length > 1)}</div></div>`;
    return h;
  }

  function rankByMake(make) {
    const regs = REGS.filter((reg) => FLEET[reg].spec.make === make);
    return rankedList(regs, S().rankTitleMake(make)) || S().rankNoData(make);
  }

  function efficiencyExtremes() {
    const regs = REGS.filter((reg) => {
      const t = FLEET[reg].trips;
      return t && t.ep_kwh_per_km?.mean != null && !t.low_sample;
    });
    return rankedList(regs, S().rankTitleFleet) || fleetOverview();
  }

  function compareMakes(makes) {
    const L = S();
    const stats = makes.map((mk) => {
      const regs = REGS.filter((reg) => FLEET[reg].spec.make === mk && FLEET[reg].trips?.ep_kwh_per_km?.mean != null);
      let wsum = 0, w = 0;
      for (const reg of regs) { const t = FLEET[reg].trips; wsum += t.ep_kwh_per_km.mean * t.n_trips; w += t.n_trips; }
      return { mk, ep: w ? wsum / w : null, n: w, count: regs.length };
    }).filter((x) => x.ep != null);
    if (stats.length < 2) return null;
    stats.sort((a, b) => a.ep - b.ep);
    let h = `<div class="veh-card"><div class="veh-head"><span class="veh-name">${L.mkTitle}</span></div>
      <table class="jolt"><thead><tr><th>${L.mkMake}</th><th>${L.mkCount}</th><th>${L.mkAvgEP}</th><th>${L.mkSample}</th></tr></thead><tbody>`;
    stats.forEach((x, i) => {
      const cls = i === 0 ? "winner" : (i === stats.length - 1 ? "loser" : "");
      h += `<tr><td class="${cls}"><b>${esc(x.mk)}</b></td><td class="num">${x.count}</td>
        <td class="num ${cls}">${num(x.ep, 3)}</td><td class="num">${intc(x.n)}</td></tr>`;
    });
    h += `</tbody></table><div class="verdict">${L.mkVerdict(stats[0].mk, num(stats[0].ep, 3))}</div></div>`;
    return h;
  }

  function glossaryCard(key) {
    const def = GLOSSARY_TR[key] ? GLOSSARY_TR[key][LANG] : "";
    return `<div class="veh-card"><div class="veh-head"><span class="veh-name">${S().glossaryTitle(key)}</span></div>
      <p>${esc(def)}</p></div>`;
  }

  function ruleEngineAnswer(q) {
    q = q.trim();
    if (!q) return S().greeting();
    const regs = findRegs(q);
    if (regs.length >= 2) return compareVehicles(regs[0], regs[1]);
    if (regs.length === 1) return vehicleCard(regs[0], wantsDetail(q));

    if (isGreeting(q) && !isOverview(q)) return S().greeting();

    const makes = findMakes(q);
    if (makes.length >= 2 && (isCompare(q) || isMostLeast(q))) {
      const cm = compareMakes(makes); if (cm) return cm;
    }
    if (makes.length === 1 && (isMostLeast(q) || isCompare(q) || isOverview(q))) return rankByMake(makes[0]);
    if (isMostLeast(q)) return efficiencyExtremes();

    const g = findGlossary(q);
    if (g) return glossaryCard(g);

    if (isOverview(q)) return fleetOverview();
    if (makes.length === 1) return rankByMake(makes[0]);

    return S().fallback();
  }

  // ╔══════════════════════════════════════════════════════════════════════╗
  // ║  桥接服务（在线 Claude 订阅模式）                                       ║
  // ╚══════════════════════════════════════════════════════════════════════╝
  async function checkBridge() {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 2500);
      const res = await fetch("/api/health", { signal: ctrl.signal });
      clearTimeout(t);
      if (!res.ok) throw new Error("bad");
      bridgeInfo = await res.json();
      bridgeOnline = true;
    } catch (_) {
      bridgeOnline = false;
    }
    updateStatus();
  }

  async function sendToBridge(message, sessionId) {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, session_id: sessionId || null, lang: LANG }),
    });
    if (!res.ok) {
      let detail = "";
      try { detail = (await res.json()).error || ""; } catch (_) {}
      throw new Error(detail || ("HTTP " + res.status));
    }
    return res.json();
  }

  // ╔══════════════════════════════════════════════════════════════════════╗
  // ║  会话状态                                                              ║
  // ╚══════════════════════════════════════════════════════════════════════╝
  function loadState() {
    try {
      const raw = localStorage.getItem(LS_KEY);
      if (raw) state = JSON.parse(raw);
    } catch (_) { state = { chats: [], currentId: null }; }
    if (!state.chats || !state.chats.length) newChat(false);
    if (!state.currentId || !state.chats.find((c) => c.id === state.currentId))
      state.currentId = state.chats[0].id;
  }
  function saveState() { try { localStorage.setItem(LS_KEY, JSON.stringify(state)); } catch (_) {} }
  function currentChat() { return state.chats.find((c) => c.id === state.currentId); }
  function isUntitled(c) { return !c.title || c.title === "新的对话" || c.title === "New conversation"; }
  function titleOf(c) { return isUntitled(c) ? S().newConversation : c.title; }
  function newChat(render) {
    const c = { id: uid(), title: "", createdAt: Date.now(), messages: [], claudeSessionId: null };
    state.chats.unshift(c); state.currentId = c.id;
    if (render !== false) { saveState(); renderAll(); elInput.focus(); }
    return c;
  }
  function deleteChat(id) {
    state.chats = state.chats.filter((c) => c.id !== id);
    if (!state.chats.length) newChat(false);
    if (state.currentId === id) state.currentId = state.chats[0].id;
    saveState(); renderAll();
  }
  function switchChat(id) { state.currentId = id; saveState(); renderAll(); closeSidebarMobile(); }

  function pushMessage(role, content, kind) {
    const c = currentChat();
    c.messages.push({ role, content, kind: kind || "text" });
    if (role === "user" && isUntitled(c)) {
      c.title = content.slice(0, 28) + (content.length > 28 ? "…" : "");
    }
    saveState();
  }

  // ╔══════════════════════════════════════════════════════════════════════╗
  // ║  渲染                                                                  ║
  // ╚══════════════════════════════════════════════════════════════════════╝
  function welcomeHtml() {
    const L = S();
    const cards = L.examples.map((g) => {
      const qs = g.qs.map((q) => `<button class="example-q" data-q="${esc(q)}">${esc(q)}</button>`).join("");
      return `<div class="example-group"><h3><span class="eg-ico">${g.ico}</span>${esc(g.title)}</h3>${qs}</div>`;
    }).join("");
    return `<div class="welcome">
      <div class="welcome-hero">
        <div class="welcome-badge">${L.welcomeBadge(AGG.n_vehicles, AGG.n_makes, AGG.total_trips_analysed)}</div>
        <h1 class="welcome-title">${esc(L.welcomeHello)}<span class="grad">${esc(L.welcomeName)}</span></h1>
        <p class="welcome-desc">${esc(L.welcomeDesc)}</p>
      </div>
      <div class="examples-grid">${cards}</div>
    </div>`;
  }

  function msgHtml(m) {
    const L = S();
    const avatar = m.role === "assistant" ? "⚡" : (LANG === "en" ? "U" : "你");
    const who = m.role === "assistant" ? L.roleAssistant : L.roleMe;
    let body;
    if (m.kind === "html") body = m.content;
    else if (m.role === "assistant") body = renderMarkdown(m.content);
    else body = esc(m.content).replace(/\n/g, "<br>");
    return `<div class="msg ${m.role}">
      <div class="avatar">${avatar}</div>
      <div class="bubble-wrap"><div class="who">${esc(who)}</div><div class="bubble">${body}</div></div>
    </div>`;
  }

  function renderChat() {
    const c = currentChat();
    elChatTitle.textContent = titleOf(c);
    if (!c.messages.length) {
      elChatScroll.innerHTML = welcomeHtml();
    } else {
      elChatScroll.innerHTML = `<div class="messages">${c.messages.map(msgHtml).join("")}</div>`;
      scrollToBottom();
    }
  }

  function renderSidebar() {
    if (!state.chats.length) { elConvList.innerHTML = `<div class="conv-empty">${esc(S().emptyChats)}</div>`; return; }
    elConvList.innerHTML = state.chats.map((c) => `
      <div class="conv-item ${c.id === state.currentId ? "active" : ""}" data-id="${c.id}">
        <span class="conv-ico">💬</span>
        <span class="conv-name">${esc(titleOf(c))}</span>
        <span class="conv-del" data-del="${c.id}" title="${esc(LANG === "en" ? "Delete" : "删除")}">
          <svg viewBox="0 0 24 24" width="14" height="14"><path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none"/></svg>
        </span>
      </div>`).join("");
  }

  function renderAll() { applyStaticI18n(); renderSidebar(); renderChat(); updateStatus(); }

  function scrollToBottom() {
    requestAnimationFrame(() => { elChatScroll.scrollTop = elChatScroll.scrollHeight; });
  }

  function showTyping() {
    let host = elChatScroll.querySelector(".messages");
    if (!host) { elChatScroll.innerHTML = `<div class="messages"></div>`; host = elChatScroll.querySelector(".messages"); }
    const div = document.createElement("div");
    div.className = "msg assistant"; div.dataset.typing = "1";
    div.innerHTML = `<div class="avatar">⚡</div><div class="bubble-wrap"><div class="who">${esc(S().roleAssistant)}</div>
      <div class="bubble"><div class="typing"><span></span><span></span><span></span></div></div></div>`;
    host.appendChild(div); scrollToBottom();
    return div;
  }
  function removeTyping(node) { if (node && node.parentNode) node.parentNode.removeChild(node); }

  // ── 语言 / 静态文案 ─────────────────────────────────────────────────────────
  function applyStaticI18n() {
    const L = S();
    document.documentElement.lang = L.htmlLang;
    const set = (sel, txt) => { const el = $(sel); if (el) el.textContent = txt; };
    set(".brand-sub", L.brandSub);
    set("#btnNewText", L.newChat);
    set("#convLabel", L.history);
    set("#modeClaude .mode-label", L.modeClaude);
    set("#modeOffline .mode-label", L.modeOffline);
    set("#apprLabel", L.appearance);
    elInput.placeholder = L.placeholder;
    $$(".lang-opt").forEach((b) => b.classList.toggle("active", b.dataset.lang === LANG));
    const fsd = $('[data-fs="down"]'), fsu = $('[data-fs="up"]');
    if (fsd) fsd.title = L.fontSmaller;
    if (fsu) fsu.title = L.fontLarger;
    updateThemeButton();
  }
  function setLang(lang) {
    if (lang === LANG || !TR[lang]) return;
    LANG = lang; localStorage.setItem(LANG_KEY, lang);
    renderAll();
  }

  // ── 主题 / 字号 ─────────────────────────────────────────────────────────────
  function updateThemeButton() {
    if (elThemeToggleText) elThemeToggleText.textContent = THEME === "dark" ? S().themeToLight : S().themeToDark;
    if (elThemeToggle) elThemeToggle.title = S().themeTitle;
  }
  function applyTheme() {
    document.documentElement.dataset.theme = THEME;
    updateThemeButton();
  }
  function toggleTheme() {
    THEME = THEME === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, THEME);
    applyTheme();
  }
  function applyFontScale() {
    document.documentElement.style.setProperty("--content-scale", String(FS));
  }
  function stepFont(dir) {
    FS = Math.min(FS_MAX, Math.max(FS_MIN, Math.round((FS + dir * FS_STEP) * 100) / 100));
    localStorage.setItem(FS_KEY, String(FS));
    applyFontScale();
  }

  // ── 模式 ──────────────────────────────────────────────────────────────────
  function effectiveMode() {
    if (modePref === "offline") return "offline";
    return bridgeOnline ? "claude" : "offline";
  }
  function setMode(pref) {
    if (pref === "claude" && !bridgeOnline) return;
    modePref = pref; localStorage.setItem(PREF_KEY, pref); updateModeUI();
  }
  function updateModeUI() {
    const L = S(); const eff = effectiveMode();
    elModeClaude.classList.toggle("active", eff === "claude");
    elModeOffline.classList.toggle("active", eff === "offline");
    elModeClaude.disabled = !bridgeOnline;
    elModeClaude.title = bridgeOnline ? L.claudeTitleOn : L.claudeTitleOff;
    if (eff === "claude") elComposerHint.innerHTML = L.hintClaude(bridgeInfo.model);
    else elComposerHint.innerHTML = bridgeOnline ? L.hintOfflineBridge : L.hintOfflineNoBridge;
  }
  function updateStatus() {
    const L = S();
    if (bridgeOnline) {
      elStatusDot.className = "dot online";
      const auth = bridgeInfo.auth_mode === "subscription" ? L.authSubscription : (bridgeInfo.auth_mode || "online");
      elStatusText.textContent = L.statusOnline(auth);
    } else {
      elStatusDot.className = "dot offline";
      elStatusText.textContent = L.statusOffline;
    }
    elFleetMini.innerHTML =
      `<div><b>${AGG.n_vehicles || 0}</b> ${L.miniVehicles}</div><div><b>${AGG.n_makes || 0}</b> ${L.miniMakes}</div>
       <div><b>${((AGG.total_trips_analysed || 0) / 1000).toFixed(1)}k</b> ${L.miniTrips}</div>
       <div><b>${Math.round((AGG.total_distance_km || 0) / 1000)}k</b> km</div>`;
    updateModeUI();
  }

  // ── 发送 ──────────────────────────────────────────────────────────────────
  let sending = false;
  async function handleSend() {
    const text = elInput.value.trim();
    if (!text || sending) return;
    sending = true; elSend.disabled = true;
    elInput.value = ""; autoGrow();

    pushMessage("user", text, "text");
    renderChat(); renderSidebar();

    if (effectiveMode() === "claude") {
      const typing = showTyping();
      try {
        const r = await sendToBridge(text, currentChat().claudeSessionId);
        removeTyping(typing);
        if (r.session_id) currentChat().claudeSessionId = r.session_id;
        pushMessage("assistant", r.reply || S().emptyReply, "text");
      } catch (e) {
        removeTyping(typing);
        const note = `<div class="note" style="color:#b45309;margin-bottom:8px">${S().bridgeFail(e.message)}</div>`;
        pushMessage("assistant", note + ruleEngineAnswer(text), "html");
        bridgeOnline = false; updateStatus();
      }
    } else {
      pushMessage("assistant", ruleEngineAnswer(text), "html");
    }
    renderChat(); renderSidebar();
    sending = false; elSend.disabled = false; elInput.focus();
  }

  function autoGrow() {
    elInput.style.height = "auto";
    elInput.style.height = Math.min(elInput.scrollHeight, 180) + "px";
  }

  function openSidebarMobile() { elSidebar.classList.add("open"); if (elScrim) elScrim.classList.add("show"); }
  function closeSidebarMobile() { elSidebar.classList.remove("open"); if (elScrim) elScrim.classList.remove("show"); }

  // ── 事件绑定 ──────────────────────────────────────────────────────────────
  function bind() {
    $("#btnNew").addEventListener("click", () => newChat());
    elSend.addEventListener("click", handleSend);
    elInput.addEventListener("input", autoGrow);
    elInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
    });
    elModeClaude.addEventListener("click", () => setMode("claude"));
    elModeOffline.addEventListener("click", () => setMode("offline"));
    const menu = $("#btnMenu"); if (menu) menu.addEventListener("click", openSidebarMobile);
    if (elScrim) elScrim.addEventListener("click", closeSidebarMobile);
    if (elThemeToggle) elThemeToggle.addEventListener("click", toggleTheme);

    document.addEventListener("click", (e) => {
      const fs = e.target.closest(".fs-btn");
      if (fs) { stepFont(fs.dataset.fs === "up" ? 1 : -1); return; }
      const lang = e.target.closest(".lang-opt");
      if (lang) { setLang(lang.dataset.lang); return; }
      const ex = e.target.closest(".example-q");
      if (ex) { elInput.value = ex.dataset.q; autoGrow(); elInput.focus(); return; }
      const del = e.target.closest("[data-del]");
      if (del) { e.stopPropagation(); deleteChat(del.dataset.del); return; }
      const item = e.target.closest(".conv-item");
      if (item) { switchChat(item.dataset.id); return; }
    });
  }

  // 调试 / 测试钩子
  if (typeof window !== "undefined") {
    window.__ruleEngineAnswer = ruleEngineAnswer;
    window.__renderMarkdown = renderMarkdown;
    window.__setLang = (l) => { LANG = l; };
  }

  // ── 启动 ──────────────────────────────────────────────────────────────────
  function init() {
    applyTheme();
    applyFontScale();
    loadState();
    bind();
    renderAll();
    checkBridge();
    setInterval(checkBridge, 15000);
    elInput.focus();
  }
  document.addEventListener("DOMContentLoaded", init);
})();
