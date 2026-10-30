// ASICS plan & timeline document (+ Jira-ready CSV) for the program team and leadership.
const fs = require("fs");
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, WidthType, ShadingType,
  AlignmentType, HeadingLevel, LevelFormat, PageOrientation, BorderStyle, VerticalAlign,
} = require("docx");

const [, , OUT_DOCX, OUT_CSV] = process.argv;

// ---- the plan: one list feeds the chart, the table and the CSV ------------------------------
// type: Epic | Story | Milestone ; dates are ISO (YYYY-MM-DD)
const ITEMS = [
  { id: "ASICS-E0", type: "Epic", summary: "Pilot: Bengaluru (Parastatal)", owner: "Program + Tech",
    start: "2026-09-01", end: "2026-09-30", status: "Done", phase: "pilot",
    notes: "Completed with inputs from the program team." },
  { id: "ASICS-0.1", parent: "ASICS-E0", type: "Story", summary: "Bengaluru pilot with program team inputs",
    owner: "Program + Tech", start: "2026-09-01", end: "2026-09-30", status: "Done", phase: "pilot" },

  { id: "ASICS-E1", type: "Epic", summary: "Phase 1: agentic setup, 1–2 cities, accurate citations and answers",
    owner: "Tech + Program", start: "2026-10-01", end: "2026-10-30", status: "In progress", phase: "p1",
    notes: "No AI scoring in this phase: accuracy of citations and answers first." },
  { id: "ASICS-1.1", parent: "ASICS-E1", type: "Story",
    summary: "Structured project in LangGraph + Python: Steps 1–2 as agents (find sources → answer with citations)",
    owner: "Tech", start: "2026-10-01", end: "2026-10-12", status: "Done", phase: "p1" },
  { id: "ASICS-1.2", parent: "ASICS-E1", type: "Story",
    summary: "Scoring sheet structure v1, as requested by the program team (Step 3)",
    owner: "Tech", start: "2026-10-05", end: "2026-10-12", status: "Done", phase: "p1" },
  { id: "ASICS-1.3", parent: "ASICS-E1", type: "Milestone",
    summary: "Demo: 1–2 cities end to end, agentic, with scoring sheet v1",
    owner: "Tech + Program", start: "2026-10-13", end: "2026-10-13", status: "Planned", phase: "p1",
    notes: "Tuesday 13 October." },
  { id: "ASICS-1.4", parent: "ASICS-E1", type: "Story",
    summary: "Citation and answer accuracy for 1–2 cities: review and tune prompts",
    owner: "Tech + Program", start: "2026-10-14", end: "2026-10-30", status: "Planned", phase: "p1",
    depends: "ASICS-1.3" },
  { id: "ASICS-1.5", parent: "ASICS-E1", type: "Story",
    summary: "Human answers and scores for 1–2 cities (the baseline)",
    owner: "Program", start: "2026-10-14", end: "2026-10-30", status: "Planned", phase: "p1",
    notes: "Needed to measure the AI against." },
  { id: "ASICS-1.6", parent: "ASICS-E1", type: "Story",
    summary: "Confirm the final question bank and scoring methodology per category",
    owner: "Program", start: "2026-10-14", end: "2026-10-23", status: "Planned", phase: "p1",
    notes: "Two versions of the Parastatal questions exist today; all steps must use one." },
  { id: "ASICS-1.7", parent: "ASICS-E1", type: "Story",
    summary: "Evals v1: compare AI with human answers, set the accuracy baseline and test suite",
    owner: "Tech + Program", start: "2026-10-19", end: "2026-10-30", status: "Planned", phase: "p1",
    depends: "ASICS-1.5" },

  { id: "ASICS-E2", type: "Epic", summary: "Phase 2: 12 cities, Parastatals then UPD and other categories",
    owner: "Tech + Program", start: "2026-11-02", end: "2026-11-20", status: "Planned", phase: "p2" },
  { id: "ASICS-2.1", parent: "ASICS-E2", type: "Story",
    summary: "Evidence and answers correct for 12 cities: Parastatals",
    owner: "Tech + Program", start: "2026-11-02", end: "2026-11-13", status: "Planned", phase: "p2",
    depends: "ASICS-1.4, ASICS-1.7" },
  { id: "ASICS-2.2", parent: "ASICS-E2", type: "Story",
    summary: "UPD and other categories: Steps 1–3 for 12 cities",
    owner: "Tech + Program", start: "2026-11-09", end: "2026-11-20", status: "Planned", phase: "p2",
    depends: "ASICS-1.6" },
  { id: "ASICS-2.3", parent: "ASICS-E2", type: "Story",
    summary: "Prompt fine-tuning with program team inputs; every change checked by evals",
    owner: "Tech + Program", start: "2026-11-02", end: "2026-11-20", status: "Planned", phase: "p2",
    depends: "ASICS-1.7" },
  { id: "ASICS-2.4", parent: "ASICS-E2", type: "Story",
    summary: "Cost estimates per city and category shared",
    owner: "Tech", start: "2026-11-02", end: "2026-11-13", status: "Planned", phase: "p2" },
  { id: "ASICS-2.5", parent: "ASICS-E2", type: "Milestone",
    summary: "Switch from the Tech4Dev API key to Janaagraha's own key",
    owner: "Janaagraha + Tech", start: "2026-11-16", end: "2026-11-16", status: "Planned", phase: "p2",
    depends: "ASICS-2.4", notes: "From mid-November." },

  { id: "ASICS-E3", type: "Epic", summary: "Phase 3: more cities, AI scoring with outputs for human review",
    owner: "Tech + Program", start: "2026-11-23", end: "2026-12-31", status: "Planned", phase: "p3",
    notes: "Target mid-December; latest end of December." },
  { id: "ASICS-3.1", parent: "ASICS-E3", type: "Story", summary: "Expand to more cities",
    owner: "Tech + Program", start: "2026-11-23", end: "2026-12-18", status: "Planned", phase: "p3",
    depends: "ASICS-2.1, ASICS-2.2" },
  { id: "ASICS-3.2", parent: "ASICS-E3", type: "Story",
    summary: "AI scoring with outputs designed for human review",
    owner: "Tech + Program", start: "2026-11-23", end: "2026-12-18", status: "Planned", phase: "p3" },
  { id: "ASICS-3.3", parent: "ASICS-E3", type: "Story",
    summary: "Evals for AI scoring against human scores",
    owner: "Tech + Program", start: "2026-11-30", end: "2026-12-18", status: "Planned", phase: "p3",
    depends: "ASICS-3.2" },
  { id: "ASICS-3.4", parent: "ASICS-E3", type: "Story",
    summary: "Review, documentation and handover to the program team",
    owner: "Tech + Program", start: "2026-12-14", end: "2026-12-31", status: "Planned", phase: "p3" },

  { id: "ASICS-E4", type: "Epic", summary: "Ways of working: weekly program + tech review",
    owner: "Program + Tech", start: "2026-10-12", end: "2026-12-31", status: "Planned", phase: "gov",
    notes: "Every week from the demo onwards (day to be agreed)." },
];

// ---- page geometry (A4; DXA: 1440 = 1 inch) -------------------------------------------------
const A4 = { width: 11906, height: 16838 };
const MARGIN = 900;
const PORTRAIT_W = A4.width - 2 * MARGIN; // 10106
const LANDSCAPE_W = A4.height - 2 * MARGIN; // 15038
const INK = "110F0F", HEAD = "DDE7F0", GRID = "BFBFBF";
const PHASE_FILL = { pilot: "BFBFBF", p1: "4F81BD", p2: "2E9C8F", p3: "E08A2E", gov: "C9C3E6" };
const PHASE_NAME = { pilot: "Pilot", p1: "Phase 1", p2: "Phase 2", p3: "Phase 3", gov: "Weekly review" };

const font = "Calibri";
const run = (text, opts = {}) => new TextRun({ text, font, size: opts.size ?? 20, bold: opts.bold,
  color: opts.color, italics: opts.italics });

// "**bold** plain" markup -> runs
function rich(text, opts = {}) {
  return text.split("**").map((part, i) => run(part, { ...opts, bold: opts.bold || i % 2 === 1 }));
}
const p = (text, opts = {}) => new Paragraph({ children: rich(text, opts),
  spacing: { after: opts.after ?? 80, before: opts.before ?? 0 }, alignment: opts.align });
const h1 = (text) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [run(text, { size: 26, bold: true, color: INK })],
  spacing: { before: 200, after: 80 } });
const bullet = (text) => new Paragraph({ numbering: { reference: "bullets", level: 0 },
  children: rich(text), spacing: { after: 40 } });

const border = { style: BorderStyle.SINGLE, size: 4, color: GRID };
const borders = { top: border, bottom: border, left: border, right: border };

function cell(text, width, opts = {}) {
  return new TableCell({
    width: { size: width, type: WidthType.DXA },
    borders,
    shading: opts.fill ? { type: ShadingType.CLEAR, color: "auto", fill: opts.fill } : undefined,
    verticalAlign: VerticalAlign.CENTER,
    margins: { top: 40, bottom: 40, left: 70, right: 70 },
    children: [new Paragraph({ alignment: opts.align, children: rich(text ?? "",
      { size: opts.size ?? 17, bold: opts.bold, color: opts.color }) })],
  });
}

function table(columns, rows, widths, opts = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  return new Table({
    width: { size: total, type: WidthType.DXA },
    columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: columns.map((c, i) => cell(c, widths[i], { fill: HEAD, bold: true })) }),
      ...rows.map((r) => new TableRow({ children: r.map((c, i) => cell(c, widths[i], opts.cell?.(r, i) ?? {})) })),
    ],
  });
}

// ---- date helpers ---------------------------------------------------------------------------
const d = (iso) => new Date(`${iso}T00:00:00`);
const fmt = (iso) => d(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" }).replace("Sept", "Sep");
const range = (it) => (it.start === it.end ? fmt(it.end) : `${fmt(it.start)} – ${fmt(it.end)}`);

// weeks for the chart: Mondays from 31 Aug to 21 Dec (pilot shown as September)
const WEEKS = [];
for (let t = d("2026-09-28"); t <= d("2026-12-28"); t = new Date(t.getTime() + 7 * 86400000)) WEEKS.push(t);

function ganttRows() {
  const shown = ITEMS.filter((it) => it.type !== "Story" || ["ASICS-1.4", "ASICS-1.5", "ASICS-1.7",
    "ASICS-2.1", "ASICS-2.2", "ASICS-2.4", "ASICS-3.1", "ASICS-3.2", "ASICS-3.3"].includes(it.id));
  return shown.map((it) => {
    const start = d(it.start), end = d(it.end);
    const cells = WEEKS.map((w) => {
      const wEnd = new Date(w.getTime() + 6 * 86400000);
      const pilotWeek = w.getTime() === WEEKS[0].getTime() && start < WEEKS[0];
      const on = (start <= wEnd && end >= w) || pilotWeek;
      if (!on) return { text: "" };
      if (it.type === "Milestone") return { text: "◆", fill: undefined, color: PHASE_FILL[it.phase] };
      if (it.phase === "gov") return { text: "●", fill: PHASE_FILL.gov };
      return { text: "", fill: PHASE_FILL[it.phase] };
    });
    const label = it.type === "Epic" ? `**${it.summary.split(":")[0]}**` : it.summary.replace(/:.*/, "");
    return { label: it.type === "Epic" ? label : `   ${it.summary}`, cells, item: it };
  });
}

function gantt() {
  const labelW = 4600, dateW = 1150;
  const weekW = Math.floor((LANDSCAPE_W - labelW - dateW) / WEEKS.length);
  const widths = [labelW, dateW, ...WEEKS.map(() => weekW)];
  const months = WEEKS.map((w) => w.toLocaleDateString("en-GB", { day: "numeric", month: "short" }));
  const header = new TableRow({ tableHeader: true, children: [
    cell("Work", labelW, { fill: HEAD, bold: true }), cell("Dates", dateW, { fill: HEAD, bold: true }),
    ...months.map((m, i) => cell(i === 0 ? "Sep" : m, weekW, { fill: HEAD, bold: true, size: 14, align: AlignmentType.CENTER })),
  ] });
  const rows = ganttRows().map((r) => new TableRow({ children: [
    cell(r.label, labelW, { size: r.item.type === "Epic" ? 17 : 15 }),
    cell(range(r.item), dateW, { size: 15 }),
    ...r.cells.map((c) => cell(c.text, weekW, { fill: c.fill, color: c.color, size: 16, align: AlignmentType.CENTER,
      bold: true })),
  ] }));
  return new Table({ width: { size: widths.reduce((a, b) => a + b, 0), type: WidthType.DXA },
    columnWidths: widths, rows: [header, ...rows] });
}

function legend() {
  const parts = [];
  for (const [k, name] of Object.entries(PHASE_NAME)) {
    parts.push(new TextRun({ text: "     ", shading: { type: ShadingType.CLEAR, color: "auto", fill: PHASE_FILL[k] }, size: 16 }));
    parts.push(run(`  ${name}     `, { size: 16 }));
  }
  parts.push(run("◆ milestone     ● weekly review", { size: 16 }));
  return new Paragraph({ children: parts, spacing: { before: 80, after: 120 } });
}

// ---- content ------------------------------------------------------------------------------
const intro = [
  new Paragraph({ children: [run("ASICS: AI-assisted assessment", { size: 36, bold: true, color: INK })], spacing: { after: 40 } }),
  p("Plan and timeline, October – December 2026 · for the ASICS program team and leadership", { size: 19, color: "595959", after: 200 }),

  h1("1. ASICS in brief"),
  p("Janaagraha's **Annual Survey of India's City-Systems (ASICS)** assesses how well Indian cities are set up to deliver a good quality of life: their laws, institutions and processes. It covers categories such as **ULG** (urban local government) and **Parastatals**, each with sections such as **Urban Planning & Design (UPD)**, and scores each city with the program team's expert methodology."),
  p("We are building an **AI-assisted research tool** that does the evidence work for each question. It finds the official sources, answers the question with a citation and quote, and drafts the score in the experts' scoring sheet for people to check. This lets ASICS cover more cities and categories with evidence anyone can trace back to its source."),

  h1("2. Where we are"),
  bullet("**Pilot completed (end of September):** Bengaluru, Parastatal category, with inputs from the program team."),
  bullet("**Phase 1 (now):** turning the pilot into a structured project in **LangGraph and Python**, so the research runs as a set of **AI agents** working step by step with checks in between."),
  bullet("**API and costs:** runs currently use **Tech4Dev's API key**. We will need **Janaagraha's own key from mid-November**, and will share **cost estimates** before then."),

  h1("3. What we will demo on Tuesday 13 October"),
  p("1–2 cities run end to end in the agentic setup, plus **v1 of the scoring sheet structure** requested by the program team:"),
  bullet("**Step 1 · Find sources:** the agent finds the city's parastatals, checks which websites are official, and builds a **Citation Sheet** of official sources. Every link is opened to confirm a person can read it, and a copy is saved. The team reviews and edits the sheet in Excel."),
  bullet("**Step 2 · Answer:** each question is answered **only from the reviewed Citation Sheet**, naming the source and quoting it word for word; the quote is checked against the saved copy."),
  bullet("**Step 3 · Score (v1):** answers go into the experts' scoring sheet. **One sheet per category** shows each question's AI score, the evidence behind it, and a highlighted column for the expert's own score. Scores add up from question to main question, agency, city and category, then the city's overall ASICS score."),
  bullet("**A simple app for the research team:** choose categories, cities and steps, follow progress, review in Excel. New categories are added by configuration (ULG and Parastatal are set up), and the instructions given to the AI can be read and refined by the team."),

  h1("4. The plan"),
  bullet("**Phase 1 · to 30 October:** accurate **citations and answers** for 1–2 cities (no AI scoring yet). The program team provides **human answers and scores for 1–2 cities** as the baseline, and we set up **evals**."),
  bullet("**Phase 2 · 2 – 20 November:** evidence and answers correct for **12 cities**, **Parastatals first, then ULG** and other categories. This needs inputs from the program and tech teams to update and fine-tune the prompts."),
  bullet("**Phase 3 · 23 November – mid/end December:** **more cities**, and **AI scoring** with outputs designed for human review."),
  bullet("**From now:** a **weekly review** with the program and tech teams so we stay aligned."),

  h1("5. How we will know it is accurate: evals"),
  p("With the program team, we will build a set of **human answers and scores** for 1–2 cities and compare the AI's against them. This sets a **baseline accuracy** and becomes a **test suite**: every time we tune the prompts or change the AI model, we rerun it and see at once whether accuracy has gone up or down. The tool already records where people and the AI agree, question by question."),

  h1("6. What we need from the program team"),
  bullet("**Human answers and scores for 1–2 cities by 30 October** (the eval baseline)."),
  bullet("**The final question bank and scoring methodology for each category**, so all three steps use the same version (by 23 October for Parastatals)."),
  bullet("**Reviewers for the weekly review**, and inputs to fine-tune prompts for each category."),
  bullet("**Janaagraha's API key by mid-November** (with leadership), after the cost estimates."),
];

const items = ITEMS.map((it) => [
  it.id, it.type, it.summary, it.parent ?? "", it.owner, fmt(it.start), fmt(it.end), it.status,
  it.depends ?? "", it.notes ?? "",
]);
const timelineSection = [
  h1("7. Timeline at a glance"),
  p("Weeks start on Mondays. To edit: change the dates in the table below and shade the week cells to match.", { size: 18, color: "595959" }),
  gantt(),
  legend(),
  h1("8. Work items (ready for Jira)"),
  p("Columns map to Jira's CSV import fields: Issue Id, Issue Type, Summary, Parent Id, Team, Start date, Due date, Status, Depends on, Description. The same list is in **ASICS_Timeline_Jira.csv** next to this document.", { size: 18, color: "595959" }),
  table(
    ["Issue Id", "Type", "Summary", "Parent Id", "Team", "Start", "Due", "Status", "Depends on", "Notes"],
    items,
    [1150, 900, 4250, 1050, 1250, 750, 750, 950, 1350, 2638],
    { cell: (r, i) => (r[1] === "Epic" ? { bold: true, fill: "F2F2F2" } : r[1] === "Milestone" && i === 2 ? { bold: true } : {}) },
  ),
];

const doc = new Document({
  creator: "Janaagraha · ASICS",
  title: "ASICS: AI-assisted assessment — plan and timeline",
  styles: { default: { document: { run: { font, size: 20 } } } },
  numbering: { config: [{ reference: "bullets", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•",
    alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 420, hanging: 260 } } } }] }] },
  sections: [
    { properties: { page: { size: A4, margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } },
      children: intro },
    { properties: { page: { size: { width: A4.width, height: A4.height, orientation: PageOrientation.LANDSCAPE },
      margin: { top: MARGIN, bottom: MARGIN, left: MARGIN, right: MARGIN } } }, children: timelineSection },
  ],
});

// ---- CSV for Jira ---------------------------------------------------------------------------
const q = (s) => `"${String(s ?? "").replace(/"/g, '""')}"`;
const csv = [["Issue Id", "Issue Type", "Summary", "Parent Id", "Team", "Start date", "Due date", "Status",
  "Depends on", "Description"].map(q).join(",")]
  .concat(ITEMS.map((it) => [it.id, it.type === "Milestone" ? "Task" : it.type, it.summary, it.parent ?? "",
    it.owner, it.start, it.end, it.status, it.depends ?? "", it.notes ?? ""].map(q).join(","))).join("\n");

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT_DOCX, buf);
  fs.writeFileSync(OUT_CSV, csv + "\n");
  console.log(OUT_DOCX, OUT_CSV);
});
