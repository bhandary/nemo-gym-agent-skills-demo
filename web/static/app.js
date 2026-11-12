const state = {
  briefing: null,
  view: null,
  renderedView: null,
  run: null,
  mode: "recorded",
  caseId: "offboard-friday",
  variant: "full_skills",
  step: 0,
  walkStep: 0,
  showTechnical: false,
  selectedSkills: null,
  compareWithoutMatrix: true,
  skill: null,
  skillDoc: 0,
  pollTimer: null,
  notice: "",
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
  tickets.append(el("p", "reward-note", "Pick one in Walk the ticket. Each card shows the request type and the category."));
  brief.append(tickets);
  if (!data.tickets.some((ticket) => ticket.case_id === state.caseId) && data.tickets.length) {
    state.caseId = data.tickets[0].case_id;
  }
}

function markTickets() {
  for (const button of document.querySelectorAll(".ticket-card")) {
    button.classList.toggle("is-on", button.dataset.case === state.caseId);
    button.setAttribute("aria-pressed", button.dataset.case === state.caseId ? "true" : "false");
  }
}

function ensureSelection() {
  if (state.selectedSkills) return;
  const choices = (state.briefing && state.briefing.skill_choices) || [];
  state.selectedSkills = choices.map((skill) => skill.name);
}

function sameSkills(left, right) {
  if (left.length !== right.length) return false;
  const wanted = new Set(right);
  return left.every((name) => wanted.has(name));
}

function primaryConfig() {
  ensureSelection();
  const configs = (state.briefing && state.briefing.configurations) || [];
  const match = configs.find((item) => !item.baseline && sameSkills(item.skills, state.selectedSkills));
  if (match) return match;
  if (!state.selectedSkills.length) return { id: "no_skills", label: "No skills", skills: [] };
  const titles = (state.briefing.skill_choices || [])
    .filter((skill) => state.selectedSkills.includes(skill.name))
    .map((skill) => skill.title);
  return { id: "selected", label: titles.join(", ") || "Selected playbooks", skills: [...state.selectedSkills] };
}

function visibleVariantIds() {
  const primary = primaryConfig();
  const ids = ["no_skills"];
  if (primary.id !== "no_skills") ids.push(primary.id);
  if (
    state.compareWithoutMatrix &&
    state.selectedSkills.includes("priority-matrix") &&
    primary.id !== "without_priority_matrix" &&
    !ids.includes("without_priority_matrix")
  ) {
    ids.push("without_priority_matrix");
  }
  return ids;
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
  const log = $("progress-log");
  if (run.log_tail && run.status === "running") {
    log.hidden = false;
    log.textContent = run.log_tail;
  } else {
    log.hidden = true;
    log.textContent = "";
  }
}

function renderAlert() {
  const box = $("alert");
  const run = state.run;
  if (state.notice && run && run.status === "running") {
    box.hidden = false;
    box.replaceChildren(
      el("h2", "", "A run is already in progress"),
      el("p", "", "Showing it. The scores update here when it finishes."),
    );
    return;
  }
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

  const visible = visibleVariantIds();
  const present = new Set(view.variants.map((variant) => variant.id));
  const missing = visible.filter((id) => !present.has(id) && id !== "no_skills");
  host.append(el("p", "eyebrow", "Same tickets, the configurations you chose"));
  host.append(el("h2", "", "What the grader awarded"));
  if (missing.length) {
    const wanted = primaryConfig();
    host.append(
      el(
        "p",
        "reward-note",
        `The scores on screen do not include “${wanted.label}”. Recorded sample has no skills, all four skills, and without the priority matrix. Run Mock or Live to score the mix you checked.`,
      ),
    );
  }
  const means = el("div", "means");
  const summary = view.comparison.summary.filter((item) => visible.includes(item.variant) && present.has(item.variant));
  for (const item of summary) {
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

  const shown = view.variants.filter((variant) => visible.includes(variant.id));
  const sheet = el("div", "sheet");
  sheet.style.setProperty("--cols", String(Math.max(shown.length, 1)));
  sheet.setAttribute("role", "table");
  const head = el("div", "sheet-row sheet-head");
  head.setAttribute("role", "row");
  const headers = ["Ticket", ...shown.map((variant) => variant.label)];
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
    for (const cell of ticket.cells.filter((item) => visible.includes(item.variant))) row.append(cellMeter(cell));
    sheet.append(row);
  }
  host.append(sheet);
  host.append(el("p", "reward-note", "Pass means the filed decision matches the policy. The bar is the reward, from 0 to 1."));
  state.renderedView = view;
}

const WALK_STEPS = [
  ["Employee request", "This is the note a teammate handed the lead. It does not name the priority or the queue."],
  ["Skills loaded", "These are the playbooks that lead was allowed to open. The comparison lead was given none."],
  ["Agent decision", "Each column is one filing. A green Pass matches the company rule. A red Miss does not."],
  ["Reward check", "The grader checks the lookups and each part of the filing. This is the rule for the ticket you picked."],
  ["Score", "Looking the facts up is worth 0.4. Matching the rule is worth 0.6. Those two parts add up to the reward."],
];

const CATEGORY_ICON = {
  access: "M7 11V8a5 5 0 0 1 10 0v3M6 11h12v9H6z",
  network: "M12 5v4M12 15v4M5 12h4M15 12h4M12 12h.01",
  email: "M4 7h16v10H4zM4 7l8 6 8-6",
  hardware: "M5 6h14v9H5zM9 19h6",
  software: "M5 5h14v14H5zM5 9h14",
  lifecycle: "M12 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM6 19c1.2-2.2 3.2-3.2 6-3.2S16.8 16.8 18 19",
  security: "M12 3l7 3v6c0 4.2-2.8 7.2-7 9-4.2-1.8-7-4.8-7-9V6z",
  mobile: "M9 3h6a1 1 0 0 1 1 1v16a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1zM11 18h2",
  status: "M12 7v5l3 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z",
};

function icon(category) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
  path.setAttribute("d", CATEGORY_ICON[category] || CATEGORY_ICON.status);
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "currentColor");
  path.setAttribute("stroke-width", "1.7");
  path.setAttribute("stroke-linecap", "round");
  path.setAttribute("stroke-linejoin", "round");
  svg.append(path);
  return svg;
}

function currentTicket() {
  return (state.briefing.tickets || []).find((ticket) => ticket.case_id === state.caseId) || state.briefing.tickets[0];
}

function pairForTicket() {
  const ticket = currentTicket();
  const byCase = (state.view && state.view.traces[ticket.case_id]) || {};
  const primary = primaryConfig();
  return {
    ticket,
    without: byCase.no_skills || null,
    withTrace: byCase[primary.id] || null,
    withLabel: primary.label,
  };
}

function scoreOf(trace) {
  if (!trace) return null;
  const step = [...trace.steps].reverse().find((item) => item.score);
  return step ? step.score : null;
}

function checkRow(check) {
  const row = el("div", `rubric ${check.passed ? "is-pass" : "is-miss"}`);
  row.append(el("span", "mark", check.passed ? "Pass" : "Miss"));
  const copy = el("div");
  copy.append(el("strong", "", check.label));
  copy.append(el("span", "", check.passed ? String(check.filed) : `Filed ${check.filed}. The rule says ${check.expected}.`));
  row.append(copy);
  return row;
}

function compareCard(title, trace, mode) {
  const card = el("article", "compare-card");
  card.append(el("h3", "", title));
  if (!trace) {
    card.append(el("p", "", "This side was not scored in the run on screen. Run Mock or Live to score it."));
    return card;
  }
  const score = scoreOf(trace);
  if (!score) {
    card.append(el("p", "", "This rollout has no score."));
    return card;
  }
  if (mode === "score") card.append(el("p", "big-score", rewardText(score.reward)));
  const checks = (score.checks || []).filter((item) => mode === "score" || item.label !== "Looked up the employee and the ticket before filing");
  if (mode === "decision") {
    const filing = checks.map((item) => item.filed).join(" · ");
    card.append(el("p", "decision-line", filing));
  }
  for (const check of checks) card.append(checkRow(check));
  return card;
}

function renderPicker() {
  ensureSelection();
  const host = $("picker");
  host.replaceChildren();
  host.append(el("p", "eyebrow", "What to score"));
  host.append(el("h2", "", "Playbooks the lead may open"));
  host.append(
    el(
      "p",
      "picker-caption",
      "These checkboxes are the same in Recorded, Mock, and Live. Leave them all on to score every playbook. Uncheck one to score the tickets without that playbook. A lead with no playbooks is always scored beside them.",
    ),
  );
  const list = el("div", "skill-checks");
  list.setAttribute("role", "group");
  list.setAttribute("aria-label", "Playbooks");
  for (const skill of state.briefing.skill_choices) {
    const label = el("label", "skill-check");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = skill.name;
    input.checked = state.selectedSkills.includes(skill.name);
    input.addEventListener("change", () => {
      const names = state.briefing.skill_choices.map((item) => item.name);
      state.selectedSkills = names.filter((name) => {
        const box = list.querySelector(`input[value="${name}"]`);
        return box && box.checked;
      });
      state.walkStep = 0;
      updatePickerSummary();
      renderResults();
      renderTrace();
    });
    label.append(input, el("span", "", skill.title));
    list.append(label);
  }
  host.append(list);
  const ablation = el("label", "skill-check wide");
  const matrix = document.createElement("input");
  matrix.type = "checkbox";
  matrix.checked = state.compareWithoutMatrix;
  matrix.addEventListener("change", () => {
    state.compareWithoutMatrix = matrix.checked;
    updatePickerSummary();
    renderResults();
    renderTrace();
  });
  ablation.append(matrix, el("span", "", "Also show these tickets with the priority matrix removed"));
  host.append(ablation);
  host.append(el("p", "picker-now", ""));
  updatePickerSummary();
}

function updatePickerSummary() {
  const node = document.querySelector(".picker-now");
  if (!node) return;
  const primary = primaryConfig();
  const parts = ["No skills"];
  if (primary.id !== "no_skills") parts.push(primary.label);
  if (
    state.compareWithoutMatrix &&
    state.selectedSkills.includes("priority-matrix") &&
    primary.id !== "without_priority_matrix"
  ) {
    parts.push("Without the priority matrix");
  }
  node.textContent = `The comparison shows ${parts.join(", ")}.`;
}

function renderTrace() {
  const host = $("trace");
  const view = state.view;
  if (!view || !state.briefing) {
    host.replaceChildren(el("p", "loading", "The walk loads with the scores."));
    return;
  }
  const pair = pairForTicket();
  const ticket = pair.ticket;
  host.replaceChildren();
  const intro = el("div", "walk-intro");
  intro.append(el("p", "eyebrow", "One ticket, one rule"));
  intro.append(el("h2", "", "Walk the ticket"));
  intro.append(
    el(
      "p",
      "walk-explain",
      "Pick a ticket, then move through five steps: the request, the playbooks, the filing, the checks, and the score.",
    ),
  );
  host.append(intro);

  const cards = el("div", "ticket-cards");
  cards.setAttribute("role", "list");
  for (const item of state.briefing.tickets) {
    const button = el("button", "ticket-card");
    button.type = "button";
    button.dataset.case = item.case_id;
    button.setAttribute("role", "listitem");
    const badge = el("span", `type-badge type-${item.ticket_type}`, item.type_label || item.ticket_type);
    const title = el("strong", "", item.title);
    const category = el("span", "category-line");
    category.append(icon(item.category), document.createTextNode(item.category_label || item.category));
    button.append(badge, title, category, el("small", "", item.ticket_id));
    button.addEventListener("click", () => {
      state.caseId = item.case_id;
      state.walkStep = 0;
      markTickets();
      renderTrace();
    });
    cards.append(button);
  }
  host.append(cards);
  markTickets();

  if (state.walkStep < 0 || state.walkStep >= WALK_STEPS.length) state.walkStep = 0;
  const stepper = el("div", "stepper");
  stepper.setAttribute("role", "tablist");
  stepper.setAttribute("aria-label", "Steps for this ticket");
  WALK_STEPS.forEach(([label], index) => {
    const button = el("button", `stepper-step ${index === state.walkStep ? "is-current" : ""}`);
    button.type = "button";
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", index === state.walkStep ? "true" : "false");
    button.append(el("span", "stepper-num", String(index + 1)));
    button.append(el("span", "", label));
    button.addEventListener("click", () => {
      state.walkStep = index;
      renderTrace();
    });
    stepper.append(button);
  });
  host.append(stepper);

  const [stepTitle, caption] = WALK_STEPS[state.walkStep];
  const card = el("article", "walk-card");
  card.setAttribute("aria-live", "polite");
  card.append(el("p", "walk-kicker", `Step ${state.walkStep + 1} of ${WALK_STEPS.length}`));
  card.append(el("h3", "", stepTitle));
  card.append(el("p", "walk-caption", caption));

  if (state.walkStep === 0) {
    card.append(el("blockquote", "request", ticket.handoff));
    card.append(el("p", "rule-line", `The company rule for this ticket: ${ticket.outcome}`));
  } else if (state.walkStep === 1) {
    const titles = new Map((state.briefing.skill_choices || []).map((skill) => [skill.name, skill.title]));
    const loaded = pair.withTrace && pair.withTrace.skills_loaded.length ? pair.withTrace.skills_loaded : pair.withLabel === "No skills" ? [] : primaryConfig().skills;
    if (!loaded.length) {
      card.append(el("p", "lead-copy", "No playbooks were loaded. The lead had the note and the tools only."));
    } else {
      const list = el("ul", "playbook-list");
      for (const name of loaded) list.append(el("li", "", titles.get(name) || name));
      card.append(list);
    }
    card.append(el("p", "", "The lead in the other column was not allowed to open any playbook."));
    if (!pair.withTrace && primaryConfig().id !== "no_skills") {
      card.append(el("p", "reward-note", "That mix is not in the scores on screen. Run Mock or Live to score it."));
    }
  } else if (state.walkStep === 2) {
    const columns = el("div", "compare");
    columns.append(compareCard("Without skills", pair.without, "decision"));
    columns.append(compareCard(pair.withLabel, pair.withTrace, "decision"));
    card.append(columns);
  } else if (state.walkStep === 3) {
    const score = scoreOf(pair.withTrace) || scoreOf(pair.without);
    if (!score || !score.checks) {
      card.append(el("p", "", "The checks appear after a scored run is on screen."));
    } else {
      const list = el("ul", "check-list");
      for (const check of score.checks) {
        list.append(el("li", "", `${check.label}. The rule says ${check.expected}.`));
      }
      card.append(list);
    }
    card.append(el("p", "rule-line", ticket.outcome));
  } else {
    const columns = el("div", "compare");
    columns.append(compareCard("Without skills", pair.without, "score"));
    columns.append(compareCard(pair.withLabel, pair.withTrace, "score"));
    card.append(columns);
  }

  const pager = el("div", "pager");
  const back = el("button", "", "Back");
  back.type = "button";
  back.disabled = state.walkStep === 0;
  back.addEventListener("click", () => {
    state.walkStep -= 1;
    renderTrace();
  });
  const next = el("button", "next", "Next");
  next.type = "button";
  next.disabled = state.walkStep >= WALK_STEPS.length - 1;
  next.addEventListener("click", () => {
    state.walkStep += 1;
    renderTrace();
  });
  pager.append(back, el("span", "", `Step ${state.walkStep + 1} of ${WALK_STEPS.length}`), next);
  card.append(pager);
  card.append(el("p", "key-hint", "The left and right arrow keys move between these steps."));

  const technical = document.createElement("details");
  technical.className = "technical";
  if (state.showTechnical) technical.open = true;
  technical.append(el("summary", "", "Show technical details"));
  technical.addEventListener("toggle", () => {
    state.showTechnical = technical.open;
  });
  const focus = pair.withTrace || pair.without;
  if (!focus) {
    technical.append(el("p", "", "No tool trace is available for this ticket."));
  } else {
    if (focus.skills_hash) {
      technical.append(el("p", "skills-meta", `Skills hash ${focus.skills_hash}.`));
    }
    const list = el("ol", "tech-list");
    focus.steps.forEach((step, index) => {
      const item = el("li", "");
      item.append(el("strong", "", `${index + 1}. ${step.title}`));
      item.append(el("span", "", step.detail || ""));
      if (step.excerpt) item.append(el("pre", "", step.excerpt));
      list.append(item);
    });
    technical.append(list);
  }
  card.append(technical);
  host.append(card);
}

function adoptRun(run, notice) {
  state.run = run;
  state.notice = notice || "";
  if (run.view) {
    state.view = run.view;
    state.walkStep = 0;
  }
  renderControls();
  renderProgress();
  renderAlert();
  renderResults();
  renderTrace();
  if (run.status === "running") {
    if (state.pollTimer) clearTimeout(state.pollTimer);
    state.pollTimer = setTimeout(() => poll(run.id), 800);
  }
  document.getElementById("comparison").scrollIntoView({ block: "start" });
}

async function startRun(event) {
  event.preventDefault();
  if (state.pollTimer) clearTimeout(state.pollTimer);
  state.notice = "";
  $("run-button").disabled = true;
  ensureSelection();
  try {
    const response = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        mode: state.mode,
        skills: state.selectedSkills,
        compare_without_matrix: state.compareWithoutMatrix,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (response.status === 409 && payload.detail && payload.detail.run) {
      adoptRun(payload.detail.run, payload.detail.message || "A run is already in progress. Showing it.");
      return;
    }
    if (!response.ok) {
      const error = new Error(errorDetail(payload));
      error.status = response.status;
      throw error;
    }
    adoptRun(payload, "");
  } catch (error) {
    $("alert").hidden = false;
    $("alert").replaceChildren(el("h2", "", "Could not start"), el("p", "", error.message));
    renderControls();
  }
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
    if (finished) state.notice = "";
    if (run.view) state.view = run.view;
    renderControls();
    renderProgress();
    renderAlert();
    if (run.view && state.renderedView !== run.view) {
      state.walkStep = 0;
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
    ensureSelection();
    renderPicker();
    const params = new URLSearchParams(location.search);
    if (params.get("ticket")) state.caseId = params.get("ticket");
    const step = Number(params.get("step"));
    if (Number.isInteger(step) && step > 0) state.walkStep = Math.min(WALK_STEPS.length, step) - 1;
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

document.addEventListener("keydown", (event) => {
  if (event.altKey || event.metaKey || event.ctrlKey) return;
  if ($("skill-dialog").open) return;
  const tag = event.target && event.target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
  event.preventDefault();
  if (event.key === "ArrowRight") state.walkStep = Math.min(WALK_STEPS.length - 1, state.walkStep + 1);
  if (event.key === "ArrowLeft") state.walkStep = Math.max(0, state.walkStep - 1);
  renderTrace();
});

$("runbar").addEventListener("submit", startRun);
$("skill-close").addEventListener("click", () => $("skill-dialog").close());
$("skill-dialog").addEventListener("click", (event) => {
  if (event.target === $("skill-dialog")) $("skill-dialog").close();
});

init();
