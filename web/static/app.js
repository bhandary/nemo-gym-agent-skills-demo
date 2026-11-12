const state = {
  briefing: null,
  view: null,
  renderedView: null,
  run: null,
  mode: "recorded",
  caseId: "offboard-friday",
  variant: "full_skills",
  step: 0,
  skill: null,
  skillDoc: 0,
  pollTimer: null,
};

const $ = (id) => document.getElementById(id);

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

function rewardText(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(1);
}

function meanText(value) {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return Number(value).toFixed(2);
}

function errorDetail(payload) {
  if (!payload) return "The request failed.";
  if (typeof payload.detail === "string") return payload.detail;
  return "The request was not accepted.";
}

async function readJson(response) {
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(errorDetail(payload));
    error.status = response.status;
    throw error;
  }
  return payload;
}

function inline(text) {
  const span = document.createElement("span");
  const parts = String(text).split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  for (const part of parts) {
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      span.append(el("code", "", part.slice(1, -1)));
    } else if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      span.append(el("strong", "", part.slice(2, -2)));
    } else if (part) {
      span.append(document.createTextNode(part));
    }
  }
  return span;
}

function renderMarkdown(markdown) {
  const root = el("div", "md");
  const lines = String(markdown || "").replace(/\r\n/g, "\n").split("\n");
  let list = null;
  let inCode = false;
  let code = null;
  const flushList = () => {
    if (list) root.append(list);
    list = null;
  };
  for (const line of lines) {
    if (line.startsWith("```")) {
      if (inCode) {
        root.append(code);
        code = null;
        inCode = false;
      } else {
        flushList();
        inCode = true;
        code = document.createElement("pre");
      }
      continue;
    }
    if (inCode) {
      code.textContent += (code.textContent ? "\n" : "") + line;
      continue;
    }
    const numbered = line.match(/^\d+\.\s+(.*)$/);
    if (numbered) {
      if (!list || list.tagName !== "OL") {
        flushList();
        list = document.createElement("ol");
      }
      const item = document.createElement("li");
      item.append(inline(numbered[1]));
      list.append(item);
      continue;
    }
    if (line.startsWith("- ")) {
      if (!list || list.tagName !== "UL") {
        flushList();
        list = document.createElement("ul");
      }
      const item = document.createElement("li");
      item.append(inline(line.slice(2)));
      list.append(item);
      continue;
    }
    flushList();
    if (!line.trim()) continue;
    if (line.startsWith("# ")) {
      root.append(el("h3", "", line.slice(2)));
      continue;
    }
    const paragraph = document.createElement("p");
    paragraph.append(inline(line));
    root.append(paragraph);
  }
  flushList();
  if (inCode && code) root.append(code);
  return root;
}

function renderModes() {
  if (!state.briefing.modes[state.mode] || !state.briefing.modes[state.mode].enabled) {
    state.mode = "recorded";
  }
  const host = $("modes");
  host.replaceChildren();
  const modes = [
    ["recorded", "Recorded sample"],
    ["mock", "Mock model"],
    ["live", "Live model"],
  ];
  for (const [id, label] of modes) {
    const info = state.briefing.modes[id];
    const wrap = document.createElement("label");
    const input = document.createElement("input");
    input.type = "radio";
    input.name = "mode";
    input.value = id;
    input.checked = state.mode === id;
    input.disabled = !info.enabled;
    if (!info.enabled && info.reason) wrap.title = info.reason;
    input.addEventListener("change", () => {
      state.mode = id;
      renderControls();
    });
    wrap.append(input, document.createTextNode(label));
    host.append(wrap);
  }
}

function renderControls() {
  const info = state.briefing.modes[state.mode];
  const running = state.run && state.run.status === "running";
  $("run-button").disabled = running || !info.enabled;
  $("run-button").textContent = running ? "Running…" : "Run demo";
  const detail = $("mode-detail");
  detail.textContent = info.enabled ? info.detail : info.reason;
}

function renderStory() {
  const brief = $("brief");
  const data = state.briefing;
  brief.replaceChildren();

  const intro = el("section", "panel");
  intro.append(el("p", "eyebrow", "The room"));
  intro.append(el("p", "lede", data.lede));
  intro.append(el("p", "reward-note", data.reward));
  brief.append(intro);

  const skills = el("section", "panel");
  skills.append(el("h2", "", `${data.skills.length} skills`));
  skills.append(el("p", "reward-note", "Open a playbook. The priority levels are in the matrix, not in the handoff."));
  const skillList = el("div", "skill-list");
  for (const skill of data.skills) {
    const button = el("button", "textish");
    button.type = "button";
    button.append(el("strong", "", skill.title));
    button.append(el("span", "", skill.description));
    button.addEventListener("click", () => openSkill(skill.name));
    skillList.append(button);
  }
  skills.append(skillList);
  brief.append(skills);

  const tickets = el("section", "panel");
  tickets.append(el("h2", "", `${data.tickets.length} tickets`));
  tickets.append(el("p", "reward-note", "Choose a ticket to walk the episode. The policy line is what the grader expects."));
  const ticketList = el("div", "ticket-list");
  ticketList.id = "ticket-list";
  for (const ticket of data.tickets) {
    const button = el("button", "ticket");
    button.type = "button";
    button.dataset.case = ticket.case_id;
    button.append(el("strong", "", `${ticket.ticket_id}  ${ticket.title}`));
    button.append(el("span", "", ticket.glance));
    button.append(el("span", "outcome", ticket.outcome));
    button.addEventListener("click", () => {
      state.caseId = ticket.case_id;
      state.step = 0;
      markTickets();
      renderTrace();
      $("trace").scrollIntoView({ block: "start" });
    });
    ticketList.append(button);
  }
  tickets.append(ticketList);
  brief.append(tickets);
  if (!data.tickets.some((ticket) => ticket.case_id === state.caseId) && data.tickets.length) {
    state.caseId = data.tickets[0].case_id;
  }
  markTickets();
}

function markTickets() {
  for (const button of document.querySelectorAll(".ticket")) {
    button.classList.toggle("is-on", button.dataset.case === state.caseId);
  }
}

function renderProgress() {
  const section = $("progress");
  const run = state.run;
  if (!run) {
    section.hidden = true;
    return;
  }
  section.hidden = false;
  const list = $("progress-list");
  list.replaceChildren();
  for (const step of run.steps) {
    const item = document.createElement("li");
    const dot = el("span", `dot ${step.state}`);
    const copy = el("div");
    copy.append(el("strong", "", step.label));
    if (step.detail) copy.append(el("small", "", step.detail));
    item.append(dot, copy);
    list.append(item);
  }
}

function renderAlert() {
  const box = $("alert");
  const run = state.run;
  if (!run || run.status !== "failed" || !run.error) {
    box.hidden = true;
    box.replaceChildren();
    return;
  }
  box.hidden = false;
  box.replaceChildren();
  box.append(el("h2", "", "This run did not finish"));
  box.append(el("p", "", run.error));
  const button = el("button", "ghost", "Show the recorded sample");
  button.type = "button";
  button.addEventListener("click", () => {
    showSample().catch((error) => {
      box.append(el("p", "", error.message));
    });
  });
  box.append(button);
  if (run.log_tail) {
    const details = document.createElement("details");
    details.className = "log-tail";
    details.append(el("summary", "", "What NeMo Gym printed"));
    details.append(el("pre", "", run.log_tail));
    box.append(details);
  }
}

function variantClass(id) {
  if (id === "full_skills") return "full";
  if (id === "without_priority_matrix") return "missing";
  return "no";
}

function cellMeter(cell) {
  const wrap = el("div", "score-cell");
  wrap.dataset.label = cell.label;
  if (cell.missing) {
    wrap.append(el("p", "", "Missing"));
    return wrap;
  }
  const line = el("div", "score-line");
  line.append(el("span", "", rewardText(cell.reward)));
  line.append(el("span", cell.passed ? "mark pass" : "mark fail", cell.passed ? "Pass" : "Fail"));
  wrap.append(line);
  const meter = el("div", `meter ${variantClass(cell.variant)}`);
  const bar = document.createElement("i");
  const width = Math.max(0, Math.min(1, Number(cell.reward) || 0)) * 100;
  bar.style.width = `${width}%`;
  meter.append(bar);
  wrap.append(meter);
  wrap.append(el("div", "plain", cell.plain));
  if (cell.gym_reward != null && Math.abs(cell.gym_reward - cell.reward) >= 0.001) {
    wrap.append(el("div", "gym-note", `Gym recorded ${rewardText(cell.gym_reward)}`));
  }
  return wrap;
}

function renderResults() {
  const host = $("comparison");
  const view = state.view;
  if (!view) {
    host.replaceChildren(el("p", "loading", "No scores loaded."));
    return;
  }
  host.classList.toggle("is-dim", Boolean(state.run && state.run.status === "running"));
  host.replaceChildren();
  const banner = $("banner");
  banner.hidden = false;
  banner.className = `banner ${view.live_model ? "live" : "mock"}`;
  banner.replaceChildren();
  const kicker = view.kind === "live" ? "Live model" : view.kind === "mock" ? "Mock model" : "Recorded sample";
  banner.append(el("strong", "", kicker));
  banner.append(el("p", "", view.source_label));

  host.append(el("p", "eyebrow", "Same tickets, three configurations"));
  host.append(el("h2", "", "What the grader awarded"));
  const means = el("div", "means");
  for (const item of view.comparison.summary) {
    const card = el("div", `mean ${item.variant === "full_skills" ? "full" : ""}`);
    const label = el("span");
    const swatch = el("i", `swatch ${variantClass(item.variant)}`);
    label.append(swatch, document.createTextNode(item.label));
    card.append(label);
    card.append(el("b", "", meanText(item.mean_reward)));
    card.append(el("span", "", `${item.correct} of ${item.total} decisions correct`));
    means.append(card);
  }
  host.append(means);

  const sheet = el("div", "sheet");
  sheet.setAttribute("role", "table");
  const head = el("div", "sheet-row sheet-head");
  head.setAttribute("role", "row");
  const headers = ["Ticket", ...view.variants.map((variant) => variant.label)];
  for (const text of headers) {
    const cell = el("div", "", text);
    cell.setAttribute("role", "columnheader");
    head.append(cell);
  }
  sheet.append(head);
  for (const ticket of view.comparison.tickets) {
    const row = el("div", "sheet-row");
    row.setAttribute("role", "row");
    const name = el("div", "name-cell");
    name.setAttribute("role", "rowheader");
    name.append(el("strong", "", `${ticket.ticket_id}`));
    name.append(el("span", "", ticket.title));
    row.append(name);
    for (const cell of ticket.cells) row.append(cellMeter(cell));
    sheet.append(row);
  }
  host.append(sheet);
  host.append(el("p", "reward-note", "Pass means the filed decision matches the policy. The bar is the reward, from 0 to 1."));
  state.renderedView = view;
}

function currentTrace() {
  if (!state.view) return null;
  const byCase = state.view.traces[state.caseId];
  if (!byCase) return null;
  return byCase[state.variant] || null;
}

function renderTrace() {
  const host = $("trace");
  const view = state.view;
  if (!view) {
    host.replaceChildren(el("p", "loading", "The episode trace loads with the scores."));
    return;
  }
  host.replaceChildren();
  const head = el("div", "trace-head");
  const titles = el("div");
  titles.append(el("p", "eyebrow", "One episode"));
  titles.append(el("h2", "", "Walk the ticket"));
  head.append(titles);
  const chips = el("div", "chips");
  chips.setAttribute("role", "group");
  chips.setAttribute("aria-label", "Which configuration");
  for (const variant of view.variants) {
    const button = el("button", `chip ${state.variant === variant.id ? "is-on" : ""}`, variant.label);
    button.type = "button";
    button.addEventListener("click", () => {
      state.variant = variant.id;
      state.step = 0;
      renderTrace();
    });
    chips.append(button);
  }
  head.append(chips);
  host.append(head);

  const trace = currentTrace();
  if (!trace) {
    host.append(el("p", "", "This configuration has no rollout for the selected ticket."));
    return;
  }
  const handoff = el("p", "handoff", trace.handoff);
  host.append(handoff);
  const meta = el("p", "skills-meta");
  if (trace.skills_loaded.length) {
    meta.textContent = `Skills offered: ${trace.skills_loaded.join(", ")}. Hash ${trace.skills_hash || "none"}.`;
  } else {
    meta.textContent = "No skills were offered on this run. The lead had the handoff and the tools only.";
  }
  host.append(meta);

  const steps = trace.steps;
  if (state.step >= steps.length) state.step = 0;
  const walker = el("div", "walker");
  const list = el("ol", "step-list");
  steps.forEach((step, index) => {
    const item = document.createElement("li");
    const button = el("button", `step ${index === state.step ? "is-current" : ""}`);
    button.type = "button";
    button.append(el("small", "", step.kind));
    button.append(el("strong", "", step.title));
    button.addEventListener("click", () => {
      state.step = index;
      renderTrace();
    });
    item.append(button);
    list.append(item);
  });
  walker.append(list);

  const body = el("div", "step-body");
  const step = steps[state.step];
  body.append(el("p", "eyebrow", step.kind));
  body.append(el("h3", "", step.title));
  body.append(el("p", "", step.detail));
  if (step.filing) {
    const filing = step.filing;
    body.append(el("p", "", `${filing.ticket_type || "—"} · ${filing.category || "—"} · ${filing.priority || "—"} · ${filing.assignment_group || "—"}. Actions ${filing.actions || "—"}.`));
    if (filing.requester_message) {
      body.append(el("p", "handoff", filing.requester_message));
    }
  }
  if (step.score) {
    const score = step.score;
    body.append(el("p", "", `Procedure ${score.procedure.toFixed(0)} · decision ${score.decision.toFixed(0)} · reward ${rewardText(score.reward)}.`));
    body.append(el("p", "", `Policy: ${score.expected_line}`));
    if (score.filed_ticket_type) {
      body.append(el("p", "", `Filed: ${score.filed_ticket_type} · ${score.filed_category} · ${score.filed_priority} · ${score.filed_assignment_group}. Actions ${score.filed_actions}.`));
    } else {
      body.append(el("p", "", "Filed: nothing."));
    }
    if (score.gym_reward != null) {
      body.append(el("p", "skills-meta", `NeMo Gym recorded reward ${rewardText(score.gym_reward)}.`));
    }
  }
  if (step.excerpt && step.kind !== "Reward") {
    const pre = document.createElement("pre");
    pre.textContent = step.excerpt;
    body.append(pre);
  } else if (step.excerpt && step.kind === "Reward" && step.excerpt !== "matches policy") {
    body.append(el("p", "skills-meta", step.excerpt));
  }
  const pager = el("div", "pager");
  const previous = el("button", "", "Previous");
  previous.type = "button";
  previous.disabled = state.step === 0;
  previous.addEventListener("click", () => {
    state.step -= 1;
    renderTrace();
  });
  const next = el("button", "", "Next");
  next.type = "button";
  next.disabled = state.step >= steps.length - 1;
  next.addEventListener("click", () => {
    state.step += 1;
    renderTrace();
  });
  pager.append(previous, el("span", "", `Step ${state.step + 1} of ${steps.length}`), next);
  body.append(pager);
  walker.append(body);
  host.append(walker);
}

function openSkill(name) {
  const skill = state.briefing.skills.find((item) => item.name === name);
  if (!skill) return;
  state.skill = skill;
  state.skillDoc = 0;
  paintSkill();
  $("skill-dialog").showModal();
}

function paintSkill() {
  const skill = state.skill;
  $("skill-kicker").textContent = skill.version ? `Skill · version ${skill.version}` : "Skill";
  $("skill-title").textContent = skill.title;
  $("skill-description").textContent = skill.description;
  const switcher = $("doc-switch");
  switcher.replaceChildren();
  skill.documents.forEach((doc, index) => {
    const button = el("button", `chip ${index === state.skillDoc ? "is-on" : ""}`, doc.label);
    button.type = "button";
    button.addEventListener("click", () => {
      state.skillDoc = index;
      paintSkill();
    });
    switcher.append(button);
  });
  const body = $("skill-body");
  body.replaceChildren(renderMarkdown(skill.documents[state.skillDoc].markdown));
}

async function showSample() {
  state.view = await readJson(await fetch("/api/sample"));
  state.step = 0;
  renderResults();
  renderTrace();
}

async function poll(id) {
  try {
    const run = await readJson(await fetch(`/api/runs/${id}`));
    const finished = run.status !== "running";
    state.run = run;
    if (run.view) {
      state.view = run.view;
      state.step = 0;
    }
    renderControls();
    renderProgress();
    renderAlert();
    if (run.view && state.renderedView !== run.view) {
      renderResults();
      renderTrace();
    } else {
      $("comparison").classList.toggle("is-dim", run.status === "running");
    }
    if (!finished) state.pollTimer = setTimeout(() => poll(id), 1000);
  } catch (error) {
    $("alert").hidden = false;
    $("alert").replaceChildren(el("h2", "", "Lost contact with the run"), el("p", "", error.message));
  }
}

async function startRun(event) {
  event.preventDefault();
  if (state.pollTimer) clearTimeout(state.pollTimer);
  $("run-button").disabled = true;
  try {
    const response = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: state.mode }),
    });
    const run = await readJson(response);
    state.run = run;
    if (run.view) {
      state.view = run.view;
      state.step = 0;
    }
    renderControls();
    renderProgress();
    renderAlert();
    renderResults();
    renderTrace();
    if (run.status === "running") state.pollTimer = setTimeout(() => poll(run.id), 800);
    document.getElementById("comparison").scrollIntoView({ block: "start" });
  } catch (error) {
    $("alert").hidden = false;
    $("alert").replaceChildren(el("h2", "", "Could not start"), el("p", "", error.message));
    renderControls();
  }
}

async function init() {
  try {
    const [briefing, sample] = await Promise.all([
      readJson(await fetch("/api/briefing")),
      readJson(await fetch("/api/sample")),
    ]);
    state.briefing = briefing;
    state.view = sample;
    renderModes();
    renderControls();
    renderStory();
    const params = new URLSearchParams(location.search);
    if (params.get("ticket")) state.caseId = params.get("ticket");
    if (params.get("variant")) state.variant = params.get("variant");
    const step = Number(params.get("step"));
    if (Number.isInteger(step) && step > 0) state.step = step - 1;
    renderResults();
    renderTrace();
    markTickets();
    if (params.get("skill")) openSkill(params.get("skill"));
    if (params.get("ticket")) $("trace").scrollIntoView();
  } catch (error) {
    $("brief").replaceChildren(el("p", "", error.message));
    $("comparison").replaceChildren(el("p", "", "The scores could not be loaded."));
  }
}

$("runbar").addEventListener("submit", startRun);
$("skill-close").addEventListener("click", () => $("skill-dialog").close());
$("skill-dialog").addEventListener("click", (event) => {
  if (event.target === $("skill-dialog")) $("skill-dialog").close();
});

init();
