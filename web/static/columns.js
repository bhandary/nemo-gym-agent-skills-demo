/* Column plan for the playbook checkboxes.

   The page and tests/test_columns.mjs both use this file. A recorded column
   is shown only when its id is one this selection would actually score.
*/
(function (root) {
  const SKILLS = [
    { name: "security-first-response", title: "Security first response" },
    { name: "ticket-classification", title: "Classify and route" },
    { name: "access-request-policy", title: "Access request policy" },
    { name: "priority-matrix", title: "Priority matrix" },
  ];

  const RECORDED_NOTE = "Not in the recorded sample - run Mock or Live to score it";
  const CHANGED_NOTE = "Selection changed - run again to score it";

  function selectionConfig(selected) {
    const chosen = new Set(selected || []);
    const skills = SKILLS.filter((skill) => chosen.has(skill.name));
    const names = skills.map((skill) => skill.name);
    if (skills.length === SKILLS.length) {
      return { id: "full_skills", label: "All four skills", skills: names };
    }
    if (!skills.length) {
      return { id: "no_skills", label: "No skills", skills: [] };
    }
    const missing = SKILLS.filter((skill) => !chosen.has(skill.name));
    if (missing.length === 1) {
      const omitted = missing[0];
      return {
        id: "without_" + omitted.name.replace(/-/g, "_"),
        label: omitted.name === "priority-matrix" ? "Without the priority matrix" : "Without " + omitted.title,
        skills: names,
      };
    }
    return { id: "selected", label: skills.map((skill) => skill.title).join(", "), skills: names };
  }

  function planColumns(selected, compareWithoutMatrix) {
    const primary = selectionConfig(selected);
    const plan = [{ id: "no_skills", label: "No skills", skills: [] }];
    if (primary.id !== "no_skills") plan.push(primary);
    const keepMatrix = compareWithoutMatrix && primary.skills.indexOf("priority-matrix") !== -1;
    if (keepMatrix && primary.id !== "without_priority_matrix") {
      const ablation = selectionConfig(primary.skills.filter((name) => name !== "priority-matrix"));
      ablation.label = "Without the priority matrix";
      if (ablation.id !== "no_skills") {
        if (plan.some((item) => item.id === ablation.id)) ablation.id = "selection_without_matrix";
        plan.push(ablation);
      }
    }
    return plan;
  }

  function sameIds(left, right) {
    if (left.length !== right.length) return false;
    return left.every((item, index) => item.id === right[index].id);
  }

  function columnView(options) {
    const planned = planColumns(options.selected, options.compareWithoutMatrix);
    const view = options.view || {};
    const known = new Map((view.variants || []).map((item) => [item.id, item]));
    const run = options.run;
    const gymRun = Boolean(
      options.mode !== "recorded" &&
      run &&
      (run.mode === "mock" || run.mode === "live") &&
      Array.isArray(run.variants) &&
      run.variants.length &&
      (run.status === "running" || run.status === "succeeded" || run.status === "failed")
    );
    let columns;
    let note = "";
    if (!gymRun && options.mode === "recorded") {
      columns = planned
        .filter((column) => known.has(column.id))
        .map((column) => ({
          id: column.id,
          label: known.get(column.id).label,
          skills: column.skills,
          pending: false,
        }));
      if (planned.some((column) => !known.has(column.id))) note = RECORDED_NOTE;
    } else if (!gymRun) {
      columns = planned.map((column) => ({
        id: column.id,
        label: column.label,
        skills: column.skills,
        pending: !known.has(column.id),
      }));
    } else {
      columns = run.variants.map((column) => ({
        id: column.id,
        label: column.label,
        skills: column.skills || [],
        pending: false,
      }));
      if (!sameIds(planned, columns)) note = CHANGED_NOTE;
    }
    return {
      columns,
      note,
      caption: "The comparison shows " + columns.map((column) => column.label).join(", ") + ".",
    };
  }

  root.TicketNowColumns = {
    planColumns,
    columnView,
    RECORDED_NOTE,
    CHANGED_NOTE,
  };
})(typeof globalThis !== "undefined" ? globalThis : this);
