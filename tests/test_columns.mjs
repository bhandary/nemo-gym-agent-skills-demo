import { readFileSync } from "node:fs";
import vm from "node:vm";

const context = {};
vm.createContext(context);
vm.runInContext(readFileSync(new URL("../web/static/columns.js", import.meta.url), "utf8"), context);
const { planColumns, columnView, RECORDED_NOTE, CHANGED_NOTE } = context.TicketNowColumns;

const ALL = [
  "security-first-response",
  "ticket-classification",
  "access-request-policy",
  "priority-matrix",
];
const sample = {
  variants: [
    { id: "no_skills", label: "No skills" },
    { id: "full_skills", label: "All four skills" },
    { id: "without_priority_matrix", label: "Without the priority matrix" },
  ],
};

function labels(view) {
  return view.columns.map((column) => column.label);
}

const full = planColumns(ALL, true);
if (full.map((column) => column.id).join() !== "no_skills,full_skills,without_priority_matrix") {
  throw new Error(`default plan ids ${full.map((column) => column.id)}`);
}

const recordedFull = columnView({ mode: "recorded", selected: ALL, compareWithoutMatrix: true, view: sample, run: null });
if (labels(recordedFull).join("|") !== "No skills|All four skills|Without the priority matrix" || recordedFull.note) {
  throw new Error(`recorded default ${JSON.stringify(recordedFull)}`);
}
if (recordedFull.caption !== "The comparison shows No skills, All four skills, Without the priority matrix.") {
  throw new Error(recordedFull.caption);
}

const withoutAccess = ALL.filter((name) => name !== "access-request-policy");
const accessPlan = planColumns(withoutAccess, true);
if (accessPlan.map((column) => `${column.id}:${column.label}`).join("|") !== [
  "no_skills:No skills",
  "without_access_request_policy:Without Access request policy",
  "selected:Without the priority matrix",
].join("|")) {
  throw new Error(`access plan ${JSON.stringify(accessPlan)}`);
}
const recordedAccess = columnView({
  mode: "recorded",
  selected: withoutAccess,
  compareWithoutMatrix: true,
  view: sample,
  run: null,
});
if (labels(recordedAccess).join("|") !== "No skills" || recordedAccess.note !== RECORDED_NOTE) {
  throw new Error(`recorded access ${JSON.stringify(recordedAccess)}`);
}
if (recordedAccess.caption !== "The comparison shows No skills.") {
  throw new Error(recordedAccess.caption);
}

const none = columnView({ mode: "recorded", selected: [], compareWithoutMatrix: true, view: sample, run: null });
if (labels(none).join("|") !== "No skills" || none.note) {
  throw new Error(`empty selection ${JSON.stringify(none)}`);
}

const noMatrix = columnView({
  mode: "recorded",
  selected: ALL.filter((name) => name !== "priority-matrix"),
  compareWithoutMatrix: true,
  view: sample,
  run: null,
});
if (labels(noMatrix).join("|") !== "No skills|Without the priority matrix" || noMatrix.note) {
  throw new Error(`matrix off ${JSON.stringify(noMatrix)}`);
}

const preview = columnView({ mode: "mock", selected: withoutAccess, compareWithoutMatrix: true, view: sample, run: null });
if (labels(preview).join("|") !== "No skills|Without Access request policy|Without the priority matrix") {
  throw new Error(`preview ${JSON.stringify(preview)}`);
}
if (preview.columns.filter((column) => column.pending).map((column) => column.id).join() !== "without_access_request_policy,selected") {
  throw new Error(`preview pending ${JSON.stringify(preview.columns)}`);
}

const run = {
  mode: "mock",
  status: "succeeded",
  variants: full.map((column) => ({ id: column.id, label: column.label, skills: column.skills })),
};
const changed = columnView({ mode: "mock", selected: withoutAccess, compareWithoutMatrix: true, view: sample, run });
if (labels(changed).join("|") !== "No skills|All four skills|Without the priority matrix" || changed.note !== CHANGED_NOTE) {
  throw new Error(`changed selection ${JSON.stringify(changed)}`);
}
if (changed.caption !== recordedFull.caption) throw new Error(changed.caption);

console.log("column plan ok");
