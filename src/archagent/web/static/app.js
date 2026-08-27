/* Archagent web client.
   Everything the user sees comes from the server's run payload; nothing here
   computes a measurement or a status of its own. */

const api = {
  async get(path, params) {
    if (params) {
      const query = new URLSearchParams(
        Object.entries(params).filter(([, value]) => value !== undefined && value !== null));
      const qs = query.toString();
      if (qs) path += (path.includes('?') ? '&' : '?') + qs;
    }
    return handle(await fetch(path));
  },
  async post(path, body) {
    return handle(await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body || {}),
    }));
  },
  async upload(path, form) {
    return handle(await fetch(path, { method: 'POST', body: form }));
  },
};

async function handle(response) {
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = { detail: text }; }
  if (!response.ok) throw new Error((data && (data.detail || data.error)) || response.statusText);
  return data;
}

const $ = (selector) => document.querySelector(selector);
const el = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};
const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g,
  (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[ch]));

const state = {
  projects: [],
  selected: null,
  run: null,
  stream: null,
  steps: [],
  seenSteps: new Set(),
};

/* ---------------------------------------------------------------- boot */
document.addEventListener('DOMContentLoaded', async () => {
  initTheme();
  bindControls();
  await Promise.all([loadHealth(), loadProjects(), loadRuns()]);
});

function initTheme() {
  const stored = localStorage.getItem('archagent-theme');
  if (stored) document.documentElement.dataset.theme = stored;
  $('#theme-toggle').addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    document.documentElement.dataset.theme = next;
    localStorage.setItem('archagent-theme', next);
  });
}

function bindControls() {
  $('#start-button').addEventListener('click', startRun);
  $('#cancel-button').addEventListener('click', cancelRun);
  $('#connection-chip').addEventListener('click', () => $('#connect-dialog').showModal());
  $('#save-key').addEventListener('click', saveKey);
  $('#engine').addEventListener('change', updateEngineNote);
  $('#cad-check').addEventListener('click', checkCad);
  $('#cad-source').addEventListener('change', checkCad);
  $('#edit-model-button').addEventListener('click', () => openModelEditor(state.selected));
  $('#edit-close').addEventListener('click', () => { $('#model-editor').hidden = true; });
  $('#edit-version').addEventListener('change', () => reloadModelEditorVersion());
  $('#tabs').addEventListener('click', (event) => {
    const button = event.target.closest('button[data-tab]');
    if (button) selectTab(button.dataset.tab);
  });
  bindDropzone();
  updateEngineNote();
}

/* ---------------------------------------------------------- connection */
async function loadHealth() {
  try {
    const health = await api.get('/api/health');
    renderConnection(health.connection);
  } catch (error) {
    toast('לא ניתן להתחבר לשרת: ' + error.message, true);
  }
}

function renderConnection(connection) {
  const chip = $('#connection-chip');
  chip.classList.toggle('ok', connection.connected);
  chip.classList.toggle('off', !connection.connected);
  const source = { api_key: 'מפתח API', profile: 'פרופיל ant', none: 'לא מחובר' }[connection.source];
  $('#connection-label').textContent = connection.connected
    ? `מחובר · ${source} · ${connection.model}`
    : 'לא מחובר לשירות של Claude';
  state.connection = connection;
  updateEngineNote();
}

async function saveKey(event) {
  event.preventDefault();
  const key = $('#api-key').value.trim();
  const model = $('#model-input').value.trim();
  try {
    renderConnection(await api.post('/api/connect', { api_key: key, model }));
    $('#api-key').value = '';
    toast('החיבור עודכן');
  } catch (error) {
    toast(error.message, true);
  }
  $('#connect-dialog').close();
}

function updateEngineNote() {
  const engine = $('#engine').value;
  const connection = state.connection || {};
  const notes = [];
  if (engine === 'claude-code') {
    notes.push('Claude Code מנהל את ההרצה ומריץ את הסוכן בעצמו; שאלות התייעצות נרשמות כפריטים פתוחים ואינן נשאלות בזמן אמת.');
    if (connection.claude_code === false) notes.push('⚠ ' + connection.claude_code_reason);
  } else {
    notes.push('הסוכן רץ בשרת ועוצר לשאול אתכם כשנדרשת החלטה תכנונית.');
  }
  if (!connection.connected && !$('#no-llm').checked) {
    notes.push('אין חיבור לשירות של Claude — ההרצה תיפול חזרה לפרסר הדטרמיניסטי.');
  }
  $('#engine-note').textContent = notes.join(' ');
}

/* ------------------------------------------------------------ live CAD */
async function checkCad() {
  const source = $('#cad-source').value.trim();
  const status = $('#cad-status');
  if (!source) {
    status.className = 'cad-status muted';
    status.textContent = 'ריק = המודל שבתוך הפרויקט. כתובת = המסמך הפתוח ברוויט, דרך התוסף. ' +
      'רץ בדוקר על אותו מחשב? כתבו host.docker.internal במקום 127.0.0.1.';
    return;
  }
  status.className = 'cad-status muted';
  status.textContent = 'בודק…';
  try {
    const result = await api.post('/api/cad', { source });
    if (result.available) {
      const detail = result.detail || {};
      // Naming the open document is the proof it is the right one.
      const parts = [detail.document || result.adapter];
      if (detail.host_version) parts.push(detail.host_version);
      if (detail.elements) parts.push(detail.elements + ' אלמנטים');
      if (detail.read_only) parts.push('לקריאה בלבד');
      status.className = 'cad-status ok';
      status.textContent = '✓ מחובר · ' + parts.join(' · ');
    } else {
      status.className = 'cad-status warn';
      status.textContent = '⚠ ' + (result.reason || 'לא זמין');
    }
  } catch (error) {
    status.className = 'cad-status warn';
    status.textContent = '⚠ ' + error.message;
  }
}

/* ------------------------------------------------------------ projects */
async function loadProjects() {
  const { projects } = await api.get('/api/projects');
  state.projects = projects;
  const list = $('#project-list');
  list.innerHTML = '';
  projects.forEach((project) => {
    const item = el('li');
    const button = el('button');
    button.type = 'button';
    button.setAttribute('aria-pressed', String(state.selected === project.project_id));
    button.append(el('strong', null, project.name));
    const meta = el('div', 'meta');
    meta.append(el('span', null, `${project.comments} הערות`));
    meta.append(el('span', 'tag', project.language === 'he' ? 'עברית' : 'אנגלית'));
    if (!project.has_model) meta.append(el('span', 'tag', 'ללא מודל'));
    button.append(meta);
    button.addEventListener('click', () => selectProject(project.project_id));
    item.append(button);
    list.append(item);
  });
  if (!state.selected && projects.length) selectProject(projects[0].project_id);
}

function selectProject(projectId) {
  state.selected = projectId;
  const project = state.projects.find((item) => item.project_id === projectId);
  $('#launch-title').textContent = project ? project.name : 'בחרו פרויקט';
  $('#launch-subtitle').textContent = project
    ? `${project.comments} הערות · ${project.files.length} קבצים · ${project.has_model ? 'מודל ניתן לעריכה' : 'ללא מודל — סימון בלבד'}`
    : '';
  $('#start-button').disabled = !project;
  $('#edit-model-button').disabled = !project || !project.has_model;
  document.querySelectorAll('#project-list button').forEach((button) => {
    button.setAttribute('aria-pressed',
      String(button.querySelector('strong').textContent === (project && project.name)));
  });
  if (project && project.language === 'he') $('#language').value = 'auto';
}

function bindDropzone() {
  const zone = $('#upload-form');
  const input = $('#upload-input');
  zone.addEventListener('click', () => input.click());
  zone.addEventListener('dragover', (event) => { event.preventDefault(); zone.classList.add('over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('over'));
  zone.addEventListener('drop', (event) => {
    event.preventDefault();
    zone.classList.remove('over');
    uploadFiles([...event.dataTransfer.files]);
  });
  input.addEventListener('change', () => uploadFiles([...input.files]));
}

function roleOf(name) {
  const lower = name.toLowerCase();
  if (/comment|הער|דריש/.test(lower) || /הערות/.test(name)) return 'municipal_comments';
  if (/zoning|constraint|תבע|תב"ע|תכנית|דרישות/.test(lower) || /תב/.test(name)) return 'constraint';
  if (/\.(json|dwg|rvt|ifc)$/.test(lower)) return 'source_model';
  return 'reference';
}

async function uploadFiles(files) {
  if (!files.length) return;
  const form = new FormData();
  form.append('name', `העלאה ${new Date().toLocaleDateString('he-IL')}`);
  files.forEach((file) => form.append(roleOf(file.name), file, file.name));
  try {
    const project = await api.upload('/api/projects', form);
    await loadProjects();
    selectProject(project.project_id);
    toast(`נוצר פרויקט חדש עם ${files.length} קבצים`);
  } catch (error) {
    toast(error.message, true);
  }
}

/* ----------------------------------------------------------------- runs */
async function loadRuns() {
  const { runs } = await api.get('/api/runs');
  const list = $('#run-list');
  list.innerHTML = '';
  if (!runs.length) { list.append(el('li', 'empty', 'עדיין לא הורצו בדיקות')); return; }
  runs.slice(0, 8).forEach((run) => {
    const item = el('li');
    item.append(el('span', null, `${run.project_id.replace('example:', '')} · ${run.mode}`));
    item.append(el('span', 'when', new Date(run.started_at).toLocaleTimeString('he-IL')));
    item.addEventListener('click', () => openRun(run.run_id));
    list.append(item);
  });
}

async function startRun() {
  if (!state.selected) return;
  setBusy(true);
  try {
    const run = await api.post('/api/runs', {
      project_id: state.selected,
      engine: $('#engine').value,
      mode: $('#mode').value,
      language: $('#language').value,
      effort: $('#effort').value || null,
      no_llm: $('#no-llm').checked,
      source: $('#cad-source').value.trim(),
    });
    openRun(run.run_id);
    loadRuns();
  } catch (error) {
    toast(error.message, true);
    setBusy(false);
  }
}

function setBusy(busy) {
  const button = $('#start-button');
  button.disabled = busy || !state.selected;
  button.querySelector('.spinner').hidden = !busy;
  button.querySelector('.label').textContent = busy ? 'רץ…' : 'התחלת בדיקה';
}

async function cancelRun() {
  if (!state.run) return;
  try { await api.post(`/api/runs/${state.run.run_id}/cancel`); } catch (error) { toast(error.message, true); }
}

function openRun(runId) {
  if (state.stream) state.stream.close();
  $('#intro').hidden = true;
  $('#live').hidden = false;
  $('#results').hidden = true;
  $('#question').hidden = true;
  $('#stream').innerHTML = '';
  state.seenSteps = new Set();
  setBusy(true);

  const stream = new EventSource(`/api/runs/${runId}/events`);
  state.stream = stream;
  stream.addEventListener('state', (message) => applyState(JSON.parse(message.data)));
  stream.addEventListener('event', (message) => applyEvent(JSON.parse(message.data)));
  stream.onerror = () => { stream.close(); };
}

function applyState(run) {
  state.run = run;
  state.steps = run.steps;
  renderSteps();
  $('#run-status').textContent = {
    starting: 'מתחיל…', running: 'רץ…', waiting: 'ממתין לתשובתכם',
    done: 'הסתיים', failed: 'נכשל',
  }[run.status] || run.status;
  if (run.question) renderQuestion(run.question); else $('#question').hidden = true;
  if (run.status === 'done' && run.result) {
    setBusy(false);
    renderResults(run.result);
    loadRuns();
  }
  if (run.status === 'failed') {
    setBusy(false);
    toast(run.error || 'ההרצה נכשלה', true);
  }
}

function applyEvent(event) {
  if (event.step) state.seenSteps.add(event.step);
  renderSteps(event.step);
  if (['audit', 'claude', 'tool', 'blocked', 'error', 'step', 'claude_result',
       'answer', 'finished', 'cancelled'].includes(event.kind)) {
    appendStreamLine(event);
  }
}

function renderSteps(activeStep) {
  const list = $('#steps');
  if (!state.steps.length) return;
  list.innerHTML = '';
  const activeIndex = state.steps.findIndex((step) => step.id === activeStep);
  state.steps.forEach((step, index) => {
    const item = el('li');
    if (step.id === activeStep) item.classList.add('active');
    else if (state.seenSteps.has(step.id) && (activeIndex === -1 || index < activeIndex)) {
      item.classList.add('done');
    }
    item.append(el('span', 'bullet'));
    item.append(el('span', null, step.he));
    list.append(item);
  });
}

function appendStreamLine(event) {
  const stream = $('#stream');
  const item = el('li', `kind-${event.kind}`);
  item.append(el('span', 'time', new Date(event.ts).toLocaleTimeString('he-IL')));
  const body = el('div');
  body.append(el('div', null, event.title || event.kind));
  if (event.detail) {
    if (event.kind === 'claude' || event.kind === 'claude_result') {
      // Claude answers in markdown; render it rather than showing the syntax.
      const prose = el('div', 'prose');
      prose.innerHTML = renderMarkdown(event.detail);
      body.append(prose);
    } else {
      body.append(el('div', 'detail', event.detail));
    }
  }
  item.append(body);
  stream.append(item);
  stream.parentElement.scrollTop = stream.parentElement.scrollHeight;
}

/* ------------------------------------------------------------ question */
function renderQuestion(question) {
  const panel = $('#question');
  panel.hidden = false;
  $('#question-title').textContent = question.title;
  $('#question-comment').textContent = question.comment_text;
  $('#question-proposal').textContent = question.proposal;
  fillList('#question-consequences', question.consequences, 'לא זוהתה השפעה משנית');
  fillList('#question-reasons', question.reasons, '—');
  $('#question-confidence').innerHTML = '';
  $('#question-confidence').append(meter(question.confidence, 0.85));

  const actions = $('#question-actions');
  actions.innerHTML = '';
  actions.append(answerButton('אישור התיקון', 'approve', 'primary'));
  (question.alternatives || []).forEach((alternative) => {
    actions.append(answerButton(`חלופה ${alternative.letter}: ${alternative.strategy}`,
      `alternative:${alternative.letter}`, 'ghost'));
  });
  actions.append(answerButton('דחייה', 'reject', 'ghost'));
  panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function answerButton(label, answer, kind) {
  const button = el('button', kind, label);
  button.type = 'button';
  button.addEventListener('click', async () => {
    document.querySelectorAll('#question-actions button').forEach((b) => (b.disabled = true));
    try {
      await api.post(`/api/runs/${state.run.run_id}/answer`, { answer });
      $('#question').hidden = true;
    } catch (error) {
      toast(error.message, true);
    }
  });
  return button;
}

function fillList(selector, values, empty) {
  const list = $(selector);
  list.innerHTML = '';
  const items = (values || []).filter(Boolean);
  if (!items.length) { list.append(el('li', 'muted', empty)); return; }
  items.forEach((value) => list.append(el('li', null, value)));
}

/* ------------------------------------------------------------- results */
const TONE_COLOUR = { good: 'var(--good)', warn: 'var(--warning)', bad: 'var(--critical)', muted: 'var(--neutral)' };

function renderResults(result) {
  $('#results').hidden = false;
  renderKpis(result);
  renderStatusChart(result);
  renderComments(result);
  renderOpenItems(result);
  renderConstraints(result);
  renderDrawing(result);
  renderReport();
  renderFiles(result);
  selectTab('comments');
  $('#results').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function renderKpis(result) {
  const kpis = $('#kpis');
  kpis.innerHTML = '';
  const tiles = [
    { label: 'הערות רישוי', value: result.kpis.comments, tone: '' },
    { label: 'טופלו', value: result.kpis.resolved, tone: 'good' },
    { label: 'שינויים במודל', value: result.kpis.changes, tone: '' },
    { label: 'פריטים פתוחים', value: result.kpis.open_items,
      tone: result.kpis.open_items ? 'warn' : 'good' },
    { label: 'תוצאת האימות', value: result.validation_label,
      tone: result.validation === 'failed' ? 'bad' : (result.validation === 'passed' ? 'good' : 'warn'),
      small: true },
  ];
  tiles.forEach((tile) => {
    const card = el('div', 'kpi');
    const value = el('div', `value ${tile.tone}`, tile.value);
    if (tile.small) value.style.fontSize = '1.1rem';
    card.append(value, el('div', 'label', tile.label));
    kpis.append(card);
  });
  if (result.llm && result.llm.model) {
    const card = el('div', 'kpi');
    const usage = result.llm.usage || {};
    const tokens = (usage.input_tokens || 0) + (usage.output_tokens || 0);
    card.append(el('div', 'value', String(result.llm.calls || 0)));
    card.append(el('div', 'label', `קריאות ל-${result.llm.model}${tokens ? ` · ${tokens.toLocaleString('he-IL')} טוקנים` : ''}`));
    $('#kpis').append(card);
  }
}

/* Status is state, not identity: it uses the reserved status colours, and every
   segment is labelled - colour never carries the meaning alone. */
function renderStatusChart(result) {
  const host = $('#status-chart');
  host.innerHTML = '';
  const order = ['good', 'warn', 'bad', 'muted'];
  const groups = new Map();
  result.comments.forEach((comment) => {
    const key = `${comment.tone}|${comment.status}`;
    groups.set(key, (groups.get(key) || 0) + 1);
  });
  const entries = [...groups.entries()]
    .map(([key, count]) => {
      const [tone, status] = key.split('|');
      return { tone, status, count };
    })
    .sort((a, b) => order.indexOf(a.tone) - order.indexOf(b.tone));
  const total = entries.reduce((sum, entry) => sum + entry.count, 0) || 1;

  const stack = el('div', 'stack');
  entries.forEach((entry) => {
    // The count is drawn inside the segment: two segments of the same tone
    // (two kinds of "open") must never read as one block.
    const segment = el('div', 'seg', entry.count / total >= 0.08 ? String(entry.count) : '');
    segment.style.flex = `${entry.count} 0 0`;
    segment.style.background = TONE_COLOUR[entry.tone];
    segment.addEventListener('mousemove', (event) =>
      showTooltip(event, `${entry.status}: ${entry.count} מתוך ${total}`));
    segment.addEventListener('mouseleave', hideTooltip);
    stack.append(segment);
  });
  host.append(stack);

  const legend = el('div', 'legend');
  entries.forEach((entry) => {
    const item = el('span', 'item');
    const swatch = el('span', 'swatch');
    swatch.style.background = TONE_COLOUR[entry.tone];
    item.append(swatch, el('span', null, entry.status), el('span', 'count', String(entry.count)));
    legend.append(item);
  });
  host.append(legend);
  $('#status-caption').textContent =
    `${result.mode} · ${result.execution} · גרסה ${result.parent_version} ← ${result.version}`;
}

function meter(value, limit) {
  const wrap = el('div', 'meter');
  const track = el('div', 'track');
  const fill = el('div', 'fill');
  fill.style.width = `${Math.max(0, Math.min(1, value)) * 100}%`;
  const tick = el('div', 'limit');
  tick.style.insetInlineStart = `${limit * 100}%`;
  track.append(fill, tick);
  wrap.append(track, el('div', 'caption', `ביטחון ${(value * 100).toFixed(0)}% · סף ${(limit * 100).toFixed(0)}%`));
  return wrap;
}

function renderComments(result) {
  const panel = $('#panel-comments');
  panel.innerHTML = '';
  result.comments.forEach((comment) => {
    const card = el('div', 'comment');
    const head = el('div', 'comment-head');
    head.append(el('span', 'comment-id', comment.id));
    head.append(el('span', `pill ${comment.tone}`, comment.status));
    head.append(el('span', 'tag', comment.department));
    if (comment.requirement_type_label) {
      head.append(el('span', 'tag', comment.requirement_type_label));
    }
    if (comment.source && comment.source !== 'rules') {
      head.append(el('span', 'tag', comment.source === 'llm+rules' ? 'מודל + כללים' : 'מודל'));
    }
    card.append(head);
    card.append(el('p', 'text', comment.text));
    if (comment.summary) card.append(el('p', 'summary', comment.summary));

    const rows = el('div', 'rows');
    if (comment.changes.length) {
      const row = el('div', 'row');
      row.append(el('span', 'k', 'תיקון'));
      const changes = el('div');
      comment.changes.forEach((change) => {
        const line = el('div', 'change');
        line.append(document.createTextNode(`${change.element} ${change.property}: `));
        // A numeric pair is read left-to-right even inside a Hebrew sentence.
        const pair = el('span', 'ltr');
        pair.dir = 'ltr';
        pair.append(document.createTextNode(String(change.before)));
        pair.append(el('span', 'arrow', '→'));
        pair.append(document.createTextNode(String(change.after)));
        line.append(pair);
        changes.append(line);
      });
      row.append(changes);
      rows.append(row);
    }
    if (comment.evidence) {
      const row = el('div', 'row');
      row.append(el('span', 'k', 'ראיה'));
      const evidence = el('span');
      evidence.append(document.createTextNode('נמדד '));
      const measurement = el('span');
      measurement.dir = 'ltr';
      measurement.textContent =
        `${comment.evidence.measured} ${comment.evidence.op} ${comment.evidence.required}`;
      evidence.append(measurement);
      evidence.append(document.createTextNode(` (${comment.evidence.tool})`));
      row.append(evidence);
      rows.append(row);
    }
    if (comment.note) {
      const row = el('div', 'row');
      row.append(el('span', 'k', 'הערה'), el('span', null, comment.note));
      rows.append(row);
    }
    (comment.triggers || []).forEach((trigger, index) => {
      const row = el('div', 'row');
      row.append(el('span', 'k', index === 0 ? 'סיבות להתייעצות' : ''));
      row.append(el('span', 'trigger', trigger));
      rows.append(row);
    });
    card.append(rows);

    const foot = el('div', 'foot');
    foot.append(meter(comment.confidence, 0.85));
    foot.append(el('span', 'muted small', `מוגבל על ידי ${comment.limiting}`));
    card.append(foot);
    panel.append(card);
  });
}

function renderOpenItems(result) {
  const panel = $('#panel-open');
  panel.innerHTML = '';
  if (!result.open_items.length) {
    panel.append(el('p', 'empty', 'אין פריטים פתוחים 🎉'));
  } else {
    panel.append(table(['מזהה', 'מדוע פתוח', 'מה נדרש'],
      result.open_items.map((item) => [item.ref, item.why, item.needed])));
  }
  const dod = el('div', 'dod');
  dod.append(el('h3', null, 'הגדרת סיום'));
  result.definition_of_done.forEach((item) => {
    const row = el('div', `item ${item.ok ? '' : 'open'}`);
    row.append(el('span', 'box', item.ok ? '✔' : '✘'));
    row.append(el('span', null, item.text));
    dod.append(row);
  });
  panel.append(dod);
}

function renderConstraints(result) {
  const panel = $('#panel-constraints');
  panel.innerHTML = '';
  const rows = result.constraints.map((constraint) => {
    const status = el('span');
    status.append(el('span', `status-dot ${constraint.status}`));
    status.append(document.createTextNode(constraint.status_label +
      (constraint.at_limit ? ' (על הגבול)' : '')));
    return [constraint.id, constraint.priority, constraint.rule,
      `${constraint.op} ${constraint.required}`, constraint.measured, status];
  });
  panel.append(table(['אילוץ', 'עדיפות', 'כלל', 'נדרש', 'נמדד', 'סטטוס'], rows));
  if (result.checks.length) {
    panel.append(el('h3', null, 'בדיקות התוכנית'));
    panel.append(table(['בדיקה', 'סטטוס', 'פירוט'], result.checks.map((check) => {
      const status = el('span');
      status.append(el('span', `status-dot ${check.status}`));
      status.append(document.createTextNode(check.status_label));
      return [check.check, status, (check.details || []).join('; ') || '—'];
    })));
  }
}

function renderDrawing(result) {
  const panel = $('#panel-drawing');
  panel.innerHTML = '';
  state.viewer = null;
  // A stream of run events can call this more than once for the same
  // completed run (an initial fetch, then the replayed terminal SSE event);
  // each async build below checks this token so a superseded call cannot
  // append its canvas after a newer one already has.
  const token = (state.drawingRenderToken = (state.drawingRenderToken || 0) + 1);
  if (!result.files.after_model) {
    // A run with no editable model (markup-only, or an older run payload)
    // still has the rendered comparison, if anything was previewed at all.
    if (result.files.comparison) {
      const frame = document.createElement('iframe');
      frame.className = 'drawing-frame';
      frame.src = `/api/runs/${state.run.run_id}/file?name=comparison`;
      frame.title = 'לפני / אחרי';
      panel.append(frame);
    } else {
      panel.append(el('p', 'empty', 'לא הופקה תצוגת לפני/אחרי'));
    }
    return;
  }
  buildInteractiveViewer(panel, result, token).catch((error) => {
    if (token === state.drawingRenderToken) panel.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
  });
}

async function buildInteractiveViewer(panel, result, token) {
  const runId = state.run.run_id;
  const [before, after] = await Promise.all([
    api.get(`/api/runs/${runId}/file?name=before_model`),
    api.get(`/api/runs/${runId}/file?name=after_model`),
  ]);
  const changeSet = result.files.change_set
    ? await api.get(`/api/runs/${runId}/file?name=change_set`) : null;

  const wrap = el('div', 'viewer');
  const toolbar = el('div', 'viewer-toolbar');
  const toggle = el('div', 'viewer-toggle');
  const beforeBtn = el('button', null, 'לפני');
  const afterBtn = el('button', 'active', 'אחרי');
  beforeBtn.type = 'button';
  afterBtn.type = 'button';
  toggle.append(beforeBtn, afterBtn);
  const resetBtn = el('button', 'ghost', 'איפוס תצוגה');
  resetBtn.type = 'button';
  toolbar.append(toggle, resetBtn,
    el('span', 'muted small viewer-hint', 'גלגלת = זום · גרירה = הזזה · קליק = פרטים'));

  const layout = el('div', 'viewer-layout');
  const stage = el('div', 'viewer-stage');
  const canvas = document.createElement('canvas');
  stage.append(canvas);
  const details = el('div', 'viewer-details');
  details.append(el('p', 'empty', 'לחצו על אלמנט לפרטים'));
  layout.append(stage, details);

  if (token !== state.drawingRenderToken) return;   // a newer render has since started
  wrap.append(toolbar, layout);
  panel.append(wrap);

  const viewer = new PlanViewer(canvas, details, { before, after, changeSet, result });
  state.viewer = viewer;
  resetBtn.addEventListener('click', () => viewer.resetView());
  beforeBtn.addEventListener('click', () => {
    viewer.show('before');
    beforeBtn.classList.add('active');
    afterBtn.classList.remove('active');
  });
  afterBtn.addEventListener('click', () => {
    viewer.show('after');
    afterBtn.classList.add('active');
    beforeBtn.classList.remove('active');
  });
}

/* ------------------------------------------------------------- plan viewer
   A pannable, zoomable canvas over the raw model - not a picture of it. Every
   number it shows (a dimension, a before/after value, which comment caused a
   change) is read from the same run payload the rest of the page uses;
   nothing here measures or infers anything of its own. */
function _formatChangeValue(value) {
  if (value && typeof value === 'object') {
    if ('x' in value && 'y' in value && 'w' in value && 'h' in value) {
      return `(${value.x}, ${value.y}, ${value.w}, ${value.h})`;
    }
    return JSON.stringify(value);
  }
  return String(value);
}

const CATEGORY_COLOUR = {
  building: '#7c8ba1', wall: '#8f8f8f', parking: '#5b9bf2', driveway: '#c9a24b',
  room: '#7fb0e0', door: '#b88a4a', window: '#7ec8c8', stair: '#a56bd6',
  railing: '#9a9a9a', floor: '#8f8f8f', roof: '#8b6b4a', column: '#6f6f6f',
  sidewalk: '#b8b09a', site: 'transparent', dimension: '#a8a8a8', text: '#a8a8a8',
  generic: '#909090',
};

class PlanViewer {
  constructor(canvas, detailsEl, data) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.detailsEl = detailsEl;
    this.models = { before: data.before, after: data.after };
    this.changeSet = data.changeSet;
    this.result = data.result;
    this.which = 'after';
    this.changedIds = new Set(this.changeSet ? this.changeSet.highlight || [] : []);
    this.elementsByComment = this._indexByComment();
    this.scale = 1;
    this.offset = { x: 0, y: 0 };
    this.selected = null;
    this.dragging = null;

    this._bindEvents();
    this._resizeObserver = new ResizeObserver(() => this._draw());
    this._resizeObserver.observe(canvas.parentElement);
    this.resetView();
  }

  _indexByComment() {
    const map = new Map();
    if (!this.changeSet) return map;
    (this.changeSet.by_comment || []).forEach((entry) => {
      entry.elements.forEach((id) => {
        if (!map.has(id)) map.set(id, []);
        map.get(id).push(entry);
      });
    });
    return map;
  }

  show(which) {
    this.which = which;
    this.selected = null;
    this._renderDetails(null);
    this._draw();
  }

  elements() {
    return (this.models[this.which] || {}).elements || [];
  }

  resetView() {
    const elements = this.elements();
    const box = elements.reduce((acc, element) => {
      const g = element.geometry || {};
      const x0 = g.x ?? 0, y0 = g.y ?? 0, x1 = x0 + (g.w ?? 0), y1 = y0 + (g.h ?? 0);
      return {
        minX: Math.min(acc.minX, x0), minY: Math.min(acc.minY, y0),
        maxX: Math.max(acc.maxX, x1), maxY: Math.max(acc.maxY, y1),
      };
    }, { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity });
    if (!isFinite(box.minX)) { box.minX = 0; box.minY = 0; box.maxX = 10; box.maxY = 10; }
    const width = Math.max(box.maxX - box.minX, 1);
    const height = Math.max(box.maxY - box.minY, 1);
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const padding = 40;
    this.scale = Math.max(Math.min(
      (rect.width - padding * 2) / width, (rect.height - padding * 2) / height), 0.001);
    // Screen y flips plan y (north is up in the model, down on screen); the
    // flip pivots on the plan's north edge, so the offset is measured from
    // there rather than from the origin.
    this.extentMaxY = box.maxY;
    this.offset = {
      x: (rect.width - width * this.scale) / 2 - box.minX * this.scale,
      y: (rect.height - height * this.scale) / 2,
    };
    this._draw();
  }

  _toScreen(x, y) {
    return { x: this.offset.x + x * this.scale, y: this.offset.y + (this.extentMaxY - y) * this.scale };
  }

  _toWorld(sx, sy) {
    return { x: (sx - this.offset.x) / this.scale, y: this.extentMaxY - (sy - this.offset.y) / this.scale };
  }

  _bindEvents() {
    this.canvas.addEventListener('wheel', (event) => {
      event.preventDefault();
      const rect = this.canvas.getBoundingClientRect();
      const cursor = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      const before = this._toWorld(cursor.x, cursor.y);
      this.scale *= event.deltaY < 0 ? 1.12 : 1 / 1.12;
      const after = this._toScreen(before.x, before.y);
      this.offset.x += cursor.x - after.x;
      this.offset.y += cursor.y - after.y;
      this._draw();
    }, { passive: false });

    this.canvas.addEventListener('pointerdown', (event) => {
      this.dragging = { x: event.clientX, y: event.clientY, moved: false };
      this.canvas.setPointerCapture(event.pointerId);
    });
    this.canvas.addEventListener('pointermove', (event) => {
      if (!this.dragging) return;
      const dx = event.clientX - this.dragging.x, dy = event.clientY - this.dragging.y;
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) this.dragging.moved = true;
      this.offset.x += dx; this.offset.y += dy;
      this.dragging.x = event.clientX; this.dragging.y = event.clientY;
      this._draw();
    });
    this.canvas.addEventListener('pointerup', (event) => {
      if (this.dragging && !this.dragging.moved) this._click(event);
      this.dragging = null;
    });
  }

  _click(event) {
    const rect = this.canvas.getBoundingClientRect();
    const point = this._toWorld(event.clientX - rect.left, event.clientY - rect.top);
    const hit = this.elements().find((element) => {
      const g = element.geometry || {};
      return point.x >= (g.x ?? 0) && point.x <= (g.x ?? 0) + (g.w ?? 0) &&
             point.y >= (g.y ?? 0) && point.y <= (g.y ?? 0) + (g.h ?? 0);
    });
    this.selected = hit || null;
    this._renderDetails(hit);
    this._draw();
  }

  _renderDetails(element) {
    this.detailsEl.innerHTML = '';
    if (!element) {
      this.detailsEl.append(el('p', 'empty', 'לחצו על אלמנט לפרטים'));
      return;
    }
    this.detailsEl.append(el('h3', null, element.label || element.id));
    this.detailsEl.append(el('p', 'muted small', `${element.type} · ${element.id}`));
    const geometryChange = (this.changeSet?.elements || []).find((e) => e.element_id === element.id);
    if (geometryChange) {
      const list = el('div', 'viewer-changes');
      geometryChange.properties.forEach((change) => {
        const row = el('div', 'change');
        row.innerHTML = `${escapeHtml(change.property)}: ` +
          `<span class="ltr">${escapeHtml(_formatChangeValue(change.before))}</span>` +
          `<span class="arrow">→</span><span class="ltr">${escapeHtml(_formatChangeValue(change.after))}</span>`;
        list.append(row);
      });
      this.detailsEl.append(el('h3', null, 'שינויים'), list);
    }
    const comments = this.elementsByComment.get(element.id) || [];
    if (comments.length) {
      const list = el('ul');
      comments.forEach((entry) => {
        const item = document.createElement('li');
        item.innerHTML = `<span class="comment-id">${escapeHtml(entry.comment_id)}</span> ` +
          `${escapeHtml(entry.status_label || entry.status)} — ${escapeHtml(entry.summary || '')}`;
        list.append(item);
      });
      this.detailsEl.append(el('h3', null, 'הערות'), list);
    }
    const props = Object.entries(element.properties || {})
      .filter(([key]) => !['width_axis', 'layer'].includes(key));
    if (props.length) {
      const list = el('div', 'viewer-changes');
      props.forEach(([key, value]) => {
        const row = el('div', 'change');
        row.textContent = `${key}: ${value}`;
        list.append(row);
      });
      this.detailsEl.append(el('h3', null, 'מאפיינים'), list);
    }
  }

  _draw() {
    const canvas = this.canvas;
    const rect = canvas.parentElement.getBoundingClientRect();
    const ratio = window.devicePixelRatio || 1;
    if (canvas.width !== rect.width * ratio || canvas.height !== rect.height * ratio) {
      canvas.width = rect.width * ratio;
      canvas.height = rect.height * ratio;
      canvas.style.width = `${rect.width}px`;
      canvas.style.height = `${rect.height}px`;
    }
    const ctx = this.ctx;
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    const styles = getComputedStyle(document.documentElement);
    const surface = styles.getPropertyValue('--surface-2').trim() || '#ffffff';
    const ink = styles.getPropertyValue('--ink').trim() || '#111111';
    ctx.fillStyle = surface;
    ctx.fillRect(0, 0, rect.width, rect.height);

    this.elements().forEach((element) => {
      const g = element.geometry || {};
      const topLeft = this._toScreen(g.x ?? 0, (g.y ?? 0) + (g.h ?? 0));
      const w = (g.w ?? 0) * this.scale;
      const h = (g.h ?? 0) * this.scale;
      const changed = this.changedIds.has(element.id);
      const selected = this.selected && this.selected.id === element.id;

      ctx.fillStyle = CATEGORY_COLOUR[element.type] || CATEGORY_COLOUR.generic;
      ctx.globalAlpha = element.type === 'site' ? 0 : 0.55;
      ctx.fillRect(topLeft.x, topLeft.y, w, h);
      ctx.globalAlpha = 1;

      ctx.strokeStyle = selected ? '#5b9bf2' : (changed ? '#a58bff' : 'rgba(120,120,120,.7)');
      ctx.lineWidth = selected ? 2.5 : (changed ? 2 : 1);
      if (changed && !selected) ctx.setLineDash([5, 3]); else ctx.setLineDash([]);
      ctx.strokeRect(topLeft.x, topLeft.y, w, h);
      ctx.setLineDash([]);

      if (w > 28 && h > 14 && element.label) {
        ctx.fillStyle = ink;
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        ctx.fillText(element.label, topLeft.x + w / 2, topLeft.y + h / 2);
      }
      if (changed) {
        ctx.fillStyle = '#a58bff';
        ctx.beginPath();
        ctx.arc(topLeft.x + w - 5, topLeft.y + 5, 3.5, 0, Math.PI * 2);
        ctx.fill();
      }
    });
  }
}

/* --------------------------------------------------------- model editor
   Direct move/resize/delete on a project's own model - a second, parallel
   control surface onto the same DrawingDriver primitives the comment-driven
   pipeline already uses (archagent.manual_edit), not a second editing
   engine. Every edit still creates a new immutable version on the server;
   nothing here mutates anything in place. Reuses PlanViewer's canvas
   transform math but keeps its own, simpler details panel (move/delete
   controls instead of comment/change references), so PlanViewer itself -
   already tested against real runs - is never touched. */
class ModelEditor {
  constructor(canvas, detailsEl, projectId, version, model) {
    this.canvas = canvas;
    this.ctx = canvas.getContext('2d');
    this.detailsEl = detailsEl;
    this.projectId = projectId;
    this.version = version;
    this.model = model;
    this.scale = 1;
    this.offset = { x: 0, y: 0 };
    this.selected = null;
    this.dragging = null;
    this._bindEvents();
    this._resizeObserver = new ResizeObserver(() => this._draw());
    this._resizeObserver.observe(canvas.parentElement);
    this.resetView();
  }

  destroy() {
    this._resizeObserver.disconnect();
  }

  setModel(version, model) {
    this.version = version;
    this.model = model;
    this.selected = null;
    this._renderDetails(null);
    this.resetView();
  }

  elements() {
    return this.model.elements || [];
  }

  resetView() {
    const elements = this.elements();
    const box = elements.reduce((acc, element) => {
      const g = element.geometry || {};
      const x0 = g.x ?? 0, y0 = g.y ?? 0, x1 = x0 + (g.w ?? 0), y1 = y0 + (g.h ?? 0);
      return {
        minX: Math.min(acc.minX, x0), minY: Math.min(acc.minY, y0),
        maxX: Math.max(acc.maxX, x1), maxY: Math.max(acc.maxY, y1),
      };
    }, { minX: Infinity, minY: Infinity, maxX: -Infinity, maxY: -Infinity });
    if (!isFinite(box.minX)) { box.minX = 0; box.minY = 0; box.maxX = 10; box.maxY = 10; }
    const width = Math.max(box.maxX - box.minX, 1);
    const height = Math.max(box.maxY - box.minY, 1);
    const rect = this.canvas.parentElement.getBoundingClientRect();
    const padding = 40;
    this.scale = Math.max(Math.min(
      (rect.width - padding * 2) / width, (rect.height - padding * 2) / height), 0.001);
    this.extentMaxY = box.maxY;
    this.offset = {
      x: (rect.width - width * this.scale) / 2 - box.minX * this.scale,
      y: (rect.height - height * this.scale) / 2,
    };
    this._draw();
  }

  _toScreen(x, y) {
    return { x: this.offset.x + x * this.scale, y: this.offset.y + (this.extentMaxY - y) * this.scale };
  }

  _toWorld(sx, sy) {
    return { x: (sx - this.offset.x) / this.scale, y: this.extentMaxY - (sy - this.offset.y) / this.scale };
  }

  _bindEvents() {
    this.canvas.addEventListener('wheel', (event) => {
      event.preventDefault();
      const rect = this.canvas.getBoundingClientRect();
      const cursor = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      const before = this._toWorld(cursor.x, cursor.y);
      this.scale *= event.deltaY < 0 ? 1.12 : 1 / 1.12;
      const after = this._toScreen(before.x, before.y);
      this.offset.x += cursor.x - after.x;
      this.offset.y += cursor.y - after.y;
      this._draw();
    }, { passive: false });
    this.canvas.addEventListener('pointerdown', (event) => {
      this.dragging = { x: event.clientX, y: event.clientY, moved: false };
      this.canvas.setPointerCapture(event.pointerId);
    });
    this.canvas.addEventListener('pointermove', (event) => {
      if (!this.dragging) return;
      const dx = event.clientX - this.dragging.x, dy = event.clientY - this.dragging.y;
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) this.dragging.moved = true;
      this.offset.x += dx; this.offset.y += dy;
      this.dragging.x = event.clientX; this.dragging.y = event.clientY;
      this._draw();
    });
    this.canvas.addEventListener('pointerup', (event) => {
      if (this.dragging && !this.dragging.moved) this._click(event);
      this.dragging = null;
    });
  }

  _click(event) {
    const rect = this.canvas.getBoundingClientRect();
    const point = this._toWorld(event.clientX - rect.left, event.clientY - rect.top);
    const hit = this.elements().find((element) => {
      const g = element.geometry || {};
      return point.x >= (g.x ?? 0) && point.x <= (g.x ?? 0) + (g.w ?? 0) &&
             point.y >= (g.y ?? 0) && point.y <= (g.y ?? 0) + (g.h ?? 0);
    });
    this.selected = hit || null;
    this._renderDetails(hit);
    this._draw();
  }

  async _edit(action, params) {
    if (!this.selected) return;
    try {
      const body = await api.post(`/api/projects/${this.projectId}/edit`, {
        base_version: this.version, action, element_id: this.selected.id, ...params,
      });
      await refreshModelEditorVersions(this.projectId, body.version);
      this.setModel(body.version, body.model);
      toast(`נשמר כגרסה ${body.version}`);
    } catch (error) {
      toast(error.message, true);
    }
  }

  _renderDetails(element) {
    this.detailsEl.innerHTML = '';
    if (!element) {
      this.detailsEl.append(el('p', 'empty', 'לחצו על אלמנט לעריכה'));
      return;
    }
    this.detailsEl.append(el('h3', null, element.label || element.id));
    this.detailsEl.append(el('p', 'muted small', `${element.type} · ${element.id}`));

    const step = () => parseFloat($('#edit-step').value || '0.5');
    const moveRow = el('div', 'edit-move-grid');
    const arrow = (label, direction) => {
      const button = el('button', 'ghost', label);
      button.type = 'button';
      button.addEventListener('click', () => this._edit('move', { distance: step(), direction }));
      return button;
    };
    moveRow.append(arrow('↑ צפון', 'north'), arrow('↓ דרום', 'south'),
      arrow('→ מזרח', 'east'), arrow('← מערב', 'west'));
    this.detailsEl.append(el('p', 'k', 'הזזה'));
    this.detailsEl.append(moveRow);

    const deleteBtn = el('button', 'ghost danger', 'מחיקת אלמנט');
    deleteBtn.type = 'button';
    deleteBtn.addEventListener('click', () => {
      if (confirm(`למחוק את ${element.label || element.id}? הגרסה הקודמת תישאר שמורה.`)) {
        this._edit('delete', {});
      }
    });
    this.detailsEl.append(deleteBtn);
  }

  _draw() {
    const { ctx, canvas } = this;
    const rect = canvas.parentElement.getBoundingClientRect();
    canvas.width = rect.width; canvas.height = rect.height;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    this.elements().forEach((element) => {
      const g = element.geometry;
      if (!g || g.kind !== 'rect') return;
      const topLeft = this._toScreen(g.x, g.y + (g.h ?? 0));
      const w = (g.w ?? 0) * this.scale, h = (g.h ?? 0) * this.scale;
      ctx.fillStyle = CATEGORY_COLOUR[element.type] || CATEGORY_COLOUR.generic;
      ctx.globalAlpha = 0.55;
      ctx.fillRect(topLeft.x, topLeft.y, w, h);
      ctx.globalAlpha = 1;
      ctx.strokeStyle = this.selected && this.selected.id === element.id ? '#e0a02b' : '#3a3f4b';
      ctx.lineWidth = this.selected && this.selected.id === element.id ? 2.5 : 1;
      ctx.strokeRect(topLeft.x, topLeft.y, w, h);
    });
  }
}

async function openModelEditor(projectId) {
  if (!projectId) return;
  try {
    const versions = await refreshModelEditorVersions(projectId);
    const latest = versions[versions.length - 1];
    const { model } = await api.get(`/api/projects/${projectId}/model`,
      { version: latest === 'original' ? undefined : latest });
    $('#model-editor').hidden = false;
    const canvas = $('#edit-canvas');
    if (state.modelEditor) state.modelEditor.destroy();
    state.modelEditor = new ModelEditor(canvas, $('#edit-details'), projectId, latest, model);
  } catch (error) {
    toast(error.message, true);
  }
}

async function refreshModelEditorVersions(projectId, select) {
  const { versions } = await api.get(`/api/projects/${projectId}/versions`);
  const list = $('#edit-version');
  list.innerHTML = '';
  versions.forEach((version) => {
    const option = document.createElement('option');
    option.value = version; option.textContent = version;
    list.append(option);
  });
  list.value = select || versions[versions.length - 1];
  return versions;
}

async function reloadModelEditorVersion() {
  if (!state.modelEditor) return;
  const version = $('#edit-version').value;
  try {
    const { model } = await api.get(`/api/projects/${state.modelEditor.projectId}/model`,
      { version: version === 'original' ? undefined : version });
    state.modelEditor.setModel(version, model);
  } catch (error) {
    toast(error.message, true);
  }
}

async function renderReport() {
  const panel = $('#panel-report');
  panel.innerHTML = '<p class="empty">טוען דוח…</p>';
  try {
    const { markdown } = await api.get(`/api/runs/${state.run.run_id}/report`);
    panel.innerHTML = `<div class="report">${renderMarkdown(markdown)}</div>`;
  } catch (error) {
    panel.innerHTML = `<p class="empty">${escapeHtml(error.message)}</p>`;
  }
}

function renderFiles(result) {
  const panel = $('#panel-files');
  panel.innerHTML = '';
  const grid = el('div', 'file-grid');
  const labels = {
    correction_report: 'דוח התיקון', comparison: 'לפני / אחרי', highlighted: 'מפת שינויים',
    validation_report: 'דוח אימות', project_context: 'הקשר ההרצה', change_map: 'מפת שינויים (JSON)',
    dependency_graph: 'גרף תלויות', consultation: 'תמליל התייעצות', run_payload: 'סיכום מכונה',
    before: 'לפני (SVG)', after: 'אחרי (SVG)',
  };
  Object.entries(result.files).forEach(([name, filename]) => {
    const card = el('div', 'file-card');
    card.append(el('span', null, labels[name] || name));
    const link = el('a', null, filename);
    link.href = `/api/runs/${state.run.run_id}/file?name=${encodeURIComponent(name)}`;
    link.target = '_blank';
    link.rel = 'noopener';
    card.append(link);
    grid.append(card);
  });
  panel.append(grid);
}

function selectTab(tab) {
  document.querySelectorAll('#tabs button').forEach((button) =>
    button.classList.toggle('active', button.dataset.tab === tab));
  document.querySelectorAll('.tab-panels > div').forEach((panel) =>
    (panel.hidden = panel.dataset.panel !== tab));
  // The canvas was sized while its tab was hidden (0×0); a resize observer
  // does not reliably fire across that display:none -> visible transition,
  // so the viewer re-measures itself explicitly the moment it is shown.
  if (tab === 'drawing' && state.viewer) state.viewer.resetView();
}

function table(headers, rows) {
  const node = el('table', 'data');
  const head = el('thead');
  const headRow = el('tr');
  headers.forEach((header) => headRow.append(el('th', null, header)));
  head.append(headRow);
  const body = el('tbody');
  rows.forEach((cells) => {
    const row = el('tr');
    cells.forEach((cell, index) => {
      const td = el('td', index >= 3 ? 'num' : '');
      if (cell instanceof Node) td.append(cell); else td.textContent = cell ?? '';
      row.append(td);
    });
    body.append(row);
  });
  node.append(head, body);
  return node;
}

/* ------------------------------------------------------------ markdown */
function renderMarkdown(markdown) {
  const lines = markdown.replace(/\r/g, '').split('\n');
  const out = [];
  let inCode = false;
  let listOpen = false;
  let tableRows = [];

  const flushList = () => { if (listOpen) { out.push('</ul>'); listOpen = false; } };
  const flushTable = () => {
    if (!tableRows.length) return;
    const [header, ...rest] = tableRows;
    const body = rest.filter((row) => !/^\s*\|?[\s:|-]+\|?\s*$/.test(row));
    const cells = (row) => row.trim().replace(/^\||\|$/g, '').split('|').map((cell) => cell.trim());
    out.push('<table><thead><tr>' + cells(header).map((cell) => `<th>${inline(cell)}</th>`).join('') +
             '</tr></thead><tbody>' +
             body.map((row) => '<tr>' + cells(row).map((cell) => `<td>${inline(cell)}</td>`).join('') + '</tr>').join('') +
             '</tbody></table>');
    tableRows = [];
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    if (/^```/.test(line)) {
      flushList(); flushTable();
      out.push(inCode ? '</pre>' : '<pre>');
      inCode = !inCode;
      continue;
    }
    if (inCode) { out.push(escapeHtml(raw) + '\n'); continue; }
    if (/^\s*<\/?div[^>]*>\s*$/.test(line)) continue;          // the RTL wrapper
    if (/^\s*\|/.test(line)) { flushList(); tableRows.push(line); continue; }
    flushTable();
    if (!line.trim()) { flushList(); continue; }
    const heading = line.match(/^(#{1,4})\s+(.*)$/);
    if (heading) {
      flushList();
      const level = heading[1].length;
      out.push(`<h${level}>${inline(heading[2])}</h${level}>`);
      continue;
    }
    if (/^---+$/.test(line.trim())) { flushList(); out.push('<hr>'); continue; }
    if (/^>\s?/.test(line)) { flushList(); out.push(`<blockquote>${inline(line.replace(/^>\s?/, ''))}</blockquote>`); continue; }
    const bullet = line.match(/^\s*[-*]\s+(.*)$/);
    if (bullet) {
      if (!listOpen) { out.push('<ul>'); listOpen = true; }
      out.push(`<li>${inline(bullet[1])}</li>`);
      continue;
    }
    flushList();
    out.push(`<p>${inline(line)}</p>`);
  }
  flushList(); flushTable();
  if (inCode) out.push('</pre>');
  return out.join('\n');
}

function inline(text) {
  return escapeHtml(text)
    .replace(/\[([ x])\]/g, (_, mark) => (mark === 'x' ? '✔' : '☐'))
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
}

/* --------------------------------------------------------------- misc */
function showTooltip(event, text) {
  const tooltip = $('#tooltip');
  tooltip.hidden = false;
  tooltip.textContent = text;
  tooltip.style.insetInlineStart = `${event.clientX + 12}px`;
  tooltip.style.top = `${event.clientY - 30}px`;
}
function hideTooltip() { $('#tooltip').hidden = true; }

function toast(message, bad) {
  const node = el('div', `toast ${bad ? 'bad' : ''}`, message);
  $('#toasts').append(node);
  setTimeout(() => node.remove(), 6000);
}
