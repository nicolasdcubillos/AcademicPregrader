let currentJobId      = null;
let liveResults       = [];
let totalStudents     = 0;
let completedStudents = 0;
let currentSort       = 'apellido';
let activeFilters     = new Set();
let studentSearchQuery = '';
let logVisible        = false;
let _previewCodes     = [];
let _resultSeq        = 0;
let _lastRendered     = [];
let _syncTimer        = null;

function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  const next = cur === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('theme', next); } catch (e) {}
}

async function selectCourse(id) {
  try {
    await fetch('/course/select', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ course_id: id })
    });
  } catch (e) { console.warn('No se pudo cambiar de curso:', e); }
}

const MODEL_PRESETS = {
  gemini: [
    { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash — recomendado' },
    { value: 'gemini-2.5-pro',   label: 'Gemini 2.5 Pro' },
    { value: 'gemini-1.5-flash', label: 'Gemini 1.5 Flash' },
    { value: 'gemini-1.5-pro',   label: 'Gemini 1.5 Pro' },
    { value: '__custom__',       label: 'Personalizado...' },
  ],
  openai: [
    { value: 'gpt-5-mini',    label: 'GPT-5 Mini — recomendado (rápido y económico)' },
    { value: 'gpt-5-nano',    label: 'GPT-5 Nano — el más barato' },
    { value: 'gpt-5',         label: 'GPT-5' },
    { value: 'gpt-4.1-mini',  label: 'GPT-4.1 Mini' },
    { value: 'gpt-4o',        label: 'GPT-4o' },
    { value: 'gpt-4o-mini',   label: 'GPT-4o Mini' },
    { value: '__custom__',    label: 'Personalizado...' },
  ],
  azure_openai: [],
};
let _providerAvailability = { azure_openai: false, openai: false, gemini: false };

function setProviderCard(provider) {
  ['azure_openai','openai','gemini'].forEach(p => {
    const card = document.getElementById('pc-' + p);
    if (!card) return;
    card.classList.toggle('selected', p === provider);
    const r = card.querySelector('input[type=radio]');
    if (r) r.checked = (p === provider);
  });
}

function populateModels(provider, currentModel) {
  const sel     = document.getElementById('cfg-llm-model');
  const presets = MODEL_PRESETS[provider] || [];
  sel.innerHTML = presets.map(p => `<option value="${p.value}">${p.label}</option>`).join('');
  const custom = document.getElementById('cfg-llm-model-custom');
  const match  = presets.find(p => p.value === currentModel);
  if (match) { sel.value = currentModel; custom.classList.add('hidden'); }
  else if (currentModel) { sel.value = '__custom__'; custom.classList.remove('hidden'); custom.value = currentModel; }
  else { custom.classList.add('hidden'); }
}

function onProviderChange(provider) {
  if (!_providerAvailability[provider]) return;
  setProviderCard(provider);
  populateModels(provider, '');
}

function updateProviderVisibility() {
  const el = document.getElementById('llm-apikey-status');
  const available = Object.entries(_providerAvailability).filter(([, enabled]) => enabled);
  available.forEach(([provider]) => document.getElementById('pc-' + provider).classList.remove('hidden'));
  Object.entries(_providerAvailability)
    .filter(([, enabled]) => !enabled)
    .forEach(([provider]) => document.getElementById('pc-' + provider).classList.add('hidden'));
  document.getElementById('llm-model-controls').classList.toggle('hidden', available.length === 0);
  el.classList.toggle('hidden', available.length !== 0);
  el.textContent = available.length === 0 ? 'No hay proveedores de IA disponibles.' : '';
  el.style.color = 'var(--yellow)';
}

function onModelChange() {
  const sel    = document.getElementById('cfg-llm-model');
  const custom = document.getElementById('cfg-llm-model-custom');
  custom.classList.toggle('hidden', sel.value !== '__custom__');
  if (sel.value === '__custom__') custom.focus();
}

function getSelectedProvider() {
  const r = document.querySelector('input[name="llm-provider"]:checked');
  return r ? r.value : 'openai';
}

function getSelectedModel() {
  const sel = document.getElementById('cfg-llm-model');
  const provider = getSelectedProvider();
  const fallback = provider === 'gemini' ? 'gemini-2.0-flash' :
    provider === 'azure_openai' ? (MODEL_PRESETS.azure_openai[0]?.value || '') : 'gpt-5-mini';
  if (!sel) return fallback;
  if (sel.value === '__custom__')
    return document.getElementById('cfg-llm-model-custom').value.trim() || fallback;
  return sel.value || fallback;
}

loadConfig();

async function loadConfig() {
  try {
    const res = await fetch('/config');
    if (!res.ok) return;
    const cfg = await res.json();
    document.getElementById('cfg-language').value      = cfg.submission_language || 'auto';
    document.getElementById('cfg-compilation').checked = cfg.enable_compilation ?? true;
    document.getElementById('cfg-plagiarism').checked  = cfg.enable_plagiarism  ?? false;
    document.getElementById('cfg-llm').checked         = cfg.enable_llm         ?? true;
    document.getElementById('cfg-cache').checked       = cfg.enable_cache        ?? false;
    document.getElementById('cfg-comment-max').checked = cfg.comment_on_max      ?? false;
    document.getElementById('btn-campus').style.display = cfg.campus_export_enabled ? '' : 'none';
    const azureDeployment = cfg.azure_openai_deployment || '';
    MODEL_PRESETS.azure_openai = azureDeployment
      ? [{ value: azureDeployment, label: `${azureDeployment} — deployment de Azure` }]
      : [];
    _providerAvailability = {
      azure_openai: !!cfg.azure_openai_available,
      openai: !!cfg.openai_available,
      gemini: !!cfg.gemini_available
    };
    updateProviderVisibility();
    const provider = cfg.llm_provider || 'openai';
    const model    = cfg.llm_model    || 'gpt-5-mini';
    setProviderCard(provider);
    populateModels(provider, model);
    const thr = parseFloat(cfg.threshold || 0.7).toFixed(2);
    document.getElementById('cfg-threshold').value       = thr;
    document.getElementById('cfg-threshold-range').value = thr;
  } catch (e) { console.warn('Config load failed:', e); }
}

async function saveConfig() {
  const btn = document.getElementById('btn-save-cfg');
  const fb  = document.getElementById('save-feedback');
  btn.disabled = true; fb.classList.add('hidden');
  const payload = {
    submission_language: document.getElementById('cfg-language').value,
    enable_compilation:  document.getElementById('cfg-compilation').checked,
    enable_plagiarism:   document.getElementById('cfg-plagiarism').checked,
    enable_llm:          document.getElementById('cfg-llm').checked,
    enable_cache:        document.getElementById('cfg-cache').checked,
    comment_on_max:      document.getElementById('cfg-comment-max').checked,
    llm_provider:        getSelectedProvider(),
    llm_model:           getSelectedModel(),
    threshold:           parseFloat(document.getElementById('cfg-threshold').value) || 0.7,
  };
  try {
    const res = await fetch('/config', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) });
    if (res.ok) { fb.classList.remove('hidden'); setTimeout(() => fb.classList.add('hidden'), 3000); }
  } catch (e) { console.error(e); }
  btn.disabled = false;
}

function syncThreshold(v)      { document.getElementById('cfg-threshold').value       = parseFloat(v).toFixed(2); }
function syncThresholdRange(v) { document.getElementById('cfg-threshold-range').value = v; }

function openSettings()  { document.getElementById('settings-overlay').classList.remove('hidden'); }
function closeSettings() { document.getElementById('settings-overlay').classList.add('hidden'); }
function closeSettingsOutside(e) { if (e.target === document.getElementById('settings-overlay')) closeSettings(); }
document.addEventListener('keydown', e => { if (e.key === 'Escape') { closeSettings(); closeCodePreview(); closeCampus(); closeDiff(); closeHistory(); } });

// ── Historial de calificaciones ──
async function openHistory() {
  document.getElementById('history-overlay').classList.remove('hidden');
  const list = document.getElementById('history-list');
  list.innerHTML = '<p class="hist-loading">Cargando tu historial...</p>';
  try {
    const res  = await fetch('/history');
    const data = await res.json();
    renderHistoryList(data.items || []);
  } catch (e) {
    list.innerHTML = '<p class="hist-error">No se pudo cargar el historial.</p>';
  }
}
function closeHistory() { document.getElementById('history-overlay')?.classList.add('hidden'); }
function closeHistoryOutside(e) { if (e.target === e.currentTarget) closeHistory(); }

function fmtHistDate(s) {
  if (!s) return '';
  const d = new Date(String(s).replace(' ', 'T') + (String(s).includes('Z') ? '' : 'Z'));
  if (isNaN(d.getTime())) return esc(s);
  return d.toLocaleString('es-CO', { day:'2-digit', month:'short', year:'numeric', hour:'2-digit', minute:'2-digit' });
}

function renderHistoryList(items) {
  const list = document.getElementById('history-list');
  if (!items.length) {
    list.innerHTML = '<p class="hist-empty">Aún no tienes calificaciones guardadas. Corre una calificación y aparecerá aquí.</p>';
    return;
  }
  list.innerHTML = items.map(it => `
    <div class="hist-item">
      <div class="hist-item-main">
        <span class="hist-item-label" title="${esc(it.label || 'Calificación')}">${esc(it.label || 'Calificación')}</span>
        <span class="hist-item-meta">${fmtHistDate(it.updated_at || it.created_at)} · ${it.student_count} estudiante(s)</span>
      </div>
      <button class="hist-open-btn" onclick="resumeHistory('${it.job_id}')">Retomar</button>
    </div>
  `).join('');
}

async function resumeHistory(jobId) {
  try {
    const res = await fetch(`/history/${jobId}`);
    if (!res.ok) { alert('No se pudo cargar esa calificación.'); return; }
    const item = await res.json();
    closeHistory();

    liveResults = (item.results || []).map(r => ({ ...r, _id: ++_resultSeq }));
    currentJobId = jobId;
    totalStudents = liveResults.length; completedStudents = liveResults.length;
    activeFilters = new Set(); currentSort = 'apellido'; studentSearchQuery = '';
    const searchInput = document.getElementById('student-search-input');
    if (searchInput) searchInput.value = '';
    document.getElementById('search-clear-btn')?.classList.add('hidden');

    document.getElementById('landing').classList.add('landing--flow');
    document.getElementById('progress-card').classList.remove('hidden');
    document.getElementById('live-board').classList.add('hidden');
    document.getElementById('log-output').innerHTML = '<span class="log-empty">Esperando salida...</span>';

    setRunning(false);
    setStatusDot('done');
    setStatusText('Calificación cargada desde tu historial.');
    setStatusBadge('Completado', 'done');
    appendLog(`Historial cargado: "${item.label || jobId}" — ${liveResults.length} estudiante(s).`);
    showResultsCard();
  } catch (e) {
    alert('Error de red al cargar el historial.');
  }
}

// ── File upload ──
const _files = { zip: null, pdf: [] };
let enunciadoMode = 'pdf'; // 'pdf' | 'text'

function setEnunciadoMode(mode) {
  enunciadoMode = mode;
  document.getElementById('mode-btn-pdf').classList.toggle('active', mode === 'pdf');
  document.getElementById('mode-btn-text').classList.toggle('active', mode === 'text');
  document.getElementById('drop-pdf').classList.toggle('hidden', mode !== 'pdf');
  document.getElementById('drop-text').classList.toggle('hidden', mode !== 'text');
  if (mode === 'text') setTimeout(() => document.getElementById('enunciado-text')?.focus(), 50);
  updateRunButton();
}

function onEnunciadoTextInput() {
  const val = document.getElementById('enunciado-text').value;
  document.getElementById('drop-text').classList.toggle('has-content', val.trim().length > 0);
  updateRunButton();
}

function formatPdfSelection(files) {
  if (!files || !files.length) return '';
  if (files.length === 1) return files[0].name;
  return `${files.length} PDF seleccionados`;
}

function appendPregraderFiles(formData, files) {
  formData.append('zip_file', files.zip, files.zip.name);
  if (enunciadoMode === 'text') {
    formData.append('enunciado_text', document.getElementById('enunciado-text').value.trim());
  } else {
    files.pdf.forEach(file => formData.append('pdf_file', file, file.name));
  }
}

function setSelectedPdfFiles(files, append = false) {
  const selected = Array.from(files || []).filter(file => file && file.name && file.name.toLowerCase().endsWith('.pdf'));
  const combined = append ? [..._files.pdf, ...selected] : selected;
  _files.pdf = combined.filter((file, index, all) =>
    all.findIndex(candidate =>
      candidate.name === file.name &&
      candidate.size === file.size &&
      candidate.lastModified === file.lastModified
    ) === index
  );
  const zone = document.getElementById('drop-pdf');
  const nameEl = document.getElementById('pdf-filename');
  const label = formatPdfSelection(_files.pdf);
  zone.classList.toggle('has-file', _files.pdf.length > 0);
  nameEl.textContent = label;
  updateRunButton();
}

function onFileSelect(type, input) {
  if (type === 'pdf') {
    setSelectedPdfFiles(input.files, true);
    input.value = '';
    return;
  }
  const file = input.files[0]; if (!file) return;
  _files[type] = file;
  const zoneId = 'drop-zip';
  document.getElementById(zoneId).classList.add('has-file');
  document.getElementById('zip-filename').textContent = file.name;
  updateRunButton();
}

function updateRunButton() {
  const btn = document.getElementById('btn-run');
  const enunciadoReady = enunciadoMode === 'text'
    ? document.getElementById('enunciado-text').value.trim().length > 0
    : _files.pdf.length > 0;
  const both = !!(_files.zip && enunciadoReady);
  btn.disabled = !both;
  btn.classList.toggle('ready', both);
}

function onDragOver(e, zoneId) { e.preventDefault(); document.getElementById(zoneId).classList.add('drag-over'); }
function onDragLeave(zoneId)   { document.getElementById(zoneId).classList.remove('drag-over'); }
function onDrop(e, type) {
  e.preventDefault();
  const zoneId = type === 'zip' ? 'drop-zip' : 'drop-pdf';
  document.getElementById(zoneId).classList.remove('drag-over');
  if (type === 'pdf') {
    const files = Array.from(e.dataTransfer.files || []).filter(file => file && file.name && file.name.toLowerCase().endsWith('.pdf'));
    if (!files.length) { flashZone(zoneId); return; }
    setSelectedPdfFiles(files, true);
    return;
  }
  const file = e.dataTransfer.files[0]; if (!file) return;
  const ext = file.name.split('.').pop().toLowerCase();
  if (ext !== type) { flashZone(zoneId); return; }
  _files[type] = file;
  document.getElementById(zoneId).classList.add('has-file');
  document.getElementById('zip-filename').textContent = file.name;
  updateRunButton();
}
function flashZone(id) {
  const el = document.getElementById(id);
  el.classList.add('error-flash');
  setTimeout(() => el.classList.remove('error-flash'), 1600);
}

function setRunning(running) {
  const btn = document.getElementById('btn-run');
  btn.innerHTML = running
    ? '<div class="spinner"></div> Calificando...'
    : '<svg width="13" height="13" viewBox="0 0 15 15" fill="currentColor"><path d="M3 2.5l9 5-9 5V2.5z"/></svg> Iniciar Calificación';
  if (running) { btn.disabled = true; btn.classList.remove('ready'); }
  else { updateRunButton(); }
  document.getElementById('btn-cancel').classList.toggle('hidden', !running);
}

async function stopJob() {
  if (!currentJobId) return;
  const btn = document.getElementById('btn-cancel');
  btn.disabled = true; btn.textContent = 'Deteniendo...';
  try { await fetch(`/stop/${currentJobId}`, { method: 'POST' }); } catch(e) { console.error(e); }
}

async function runPregrader() {
  if (!_files.zip) { flashZone('drop-zip'); return; }
  if (enunciadoMode === 'text') {
    if (!document.getElementById('enunciado-text').value.trim()) { flashZone('drop-text'); return; }
  } else if (!_files.pdf.length) { flashZone('drop-pdf'); return; }
  await saveConfig();

  document.getElementById('log-output').innerHTML = '<span class="log-empty">Esperando salida...</span>';
  document.getElementById('log-output').style.display = 'none';
  document.querySelector('.log-toggle').textContent = 'Ver log';
  logVisible = false;
  document.getElementById('landing').classList.add('landing--flow');
  document.getElementById('progress-card').classList.remove('hidden');
  document.getElementById('live-board').classList.add('hidden');
  document.getElementById('chips-container').innerHTML = '';
  document.getElementById('live-prog-fill').style.width = '0%';
  document.getElementById('live-prog-text').textContent = 'Detectando estudiantes...';
  liveResults = []; totalStudents = 0; completedStudents = 0;
  activeFilters = new Set(); currentSort = 'apellido'; studentSearchQuery = '';
  const searchInput = document.getElementById('student-search-input');
  if (searchInput) searchInput.value = '';
  document.getElementById('search-clear-btn')?.classList.add('hidden');

  const rc = document.getElementById('results-card');
  rc.classList.add('hidden'); rc.classList.remove('fade-in');
  document.getElementById('students-grid').innerHTML = '';

  setStatusDot('running'); setStatusText('Subiendo archivos...');
  setStatusBadge('Ejecutando', ''); setRunning(true);
  document.getElementById('progress-card').scrollIntoView({ behavior: 'smooth', block: 'start' });

  const fd = new FormData();
  appendPregraderFiles(fd, _files);
  const extraNotes = (document.getElementById('extra-notes')?.value || '').trim();
  if (extraNotes) fd.append('extra_notes', extraNotes);

  let jobId;
  try {
    const res = await fetch('/run', { method: 'POST', body: fd });
    const pl  = await res.json();
    if (!res.ok) {
      appendLog('[ERROR] ' + (pl.error || 'Error desconocido'));
      setRunning(false); setStatusDot('error');
      setStatusText('Error al iniciar.'); setStatusBadge('Error','error'); return;
    }
    jobId = pl.job_id; currentJobId = jobId;
    setStatusText('Iniciando proceso...');
  } catch(e) {
    appendLog('[ERROR de red] ' + e.message);
    setRunning(false); setStatusDot('error');
    setStatusText('Error de red.'); setStatusBadge('Error','error'); return;
  }

  const es = new EventSource(`/stream/${jobId}`);
  es.onmessage = async (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === 'log') {
      appendLog(msg.data);
      if (msg.data.trim()) setStatusText(msg.data.slice(0, 90));
    } else if (msg.type === 'students_list') {
      initLiveBoard(msg.students);
    } else if (msg.type === 'student_result') {
      handleStudentResult(msg.data);
    } else if (msg.type === 'done') {
      es.close(); setRunning(false); setStatusDot('done');
      setStatusText('¡Evaluación completada!'); setStatusBadge('Completado','done');
      appendLog(''); appendLog(`${msg.count || liveResults.length} estudiante(s) evaluado(s).`);
      showResultsCard();
    } else if (msg.type === 'error') {
      es.close(); setRunning(false); setStatusDot('error');
      setStatusText('Error durante la evaluación'); setStatusBadge('Error','error');
      appendLog('[ERROR] ' + msg.data);
    } else if (msg.type === 'cancelled') {
      es.close(); setRunning(false); setStatusDot('error');
      setStatusText('Calificación cancelada'); setStatusBadge('Cancelado','error');
      appendLog(''); appendLog('Proceso detenido manualmente.');
    }
  };
  es.onerror = () => { es.close(); setRunning(false); };
}

function toggleLog() {
  const log = document.getElementById('log-output');
  const btn = document.querySelector('.log-toggle');
  logVisible = !logVisible;
  log.style.display = logVisible ? '' : 'none';
  btn.textContent   = logVisible ? 'Ocultar log' : 'Ver log';
}

function truncName(n, max) { return n.length <= max ? n : n.slice(0, max-1) + '…'; }
function gradeChipClass(n) {
  if (isNaN(n)) return 'grade-na';
  return n >= 3.5 ? 'grade-hi' : n >= 2.5 ? 'grade-mid' : 'grade-lo';
}

function initLiveBoard(students) {
  totalStudents = students.length; completedStudents = 0;
  const container = document.getElementById('chips-container');
  container.innerHTML = '';
  students.forEach(name => {
    const chip = document.createElement('div');
    chip.className = 'chip pending'; chip.dataset.name = name;
    chip.innerHTML = `<div class="chip-spinner"></div><span class="chip-name">${esc(truncName(name,22))}</span>`;
    container.appendChild(chip);
  });
  updateLiveProgress();
  document.getElementById('live-board').classList.remove('hidden');
}

function handleStudentResult(data) {
  completedStudents++; liveResults.push(data);
  data._id = ++_resultSeq;
  const name  = data.estudiante || '';
  const tot   = parseFloat(data.nota);
  const cls   = gradeChipClass(tot);
  const grade = isNaN(tot) ? '—' : tot.toFixed(1);
  const chips = document.querySelectorAll('#chips-container .chip');
  let chip = null;
  chips.forEach(c => { if (c.dataset.name === name) chip = c; });
  if (!chip) { chip = document.createElement('div'); chip.dataset.name = name; document.getElementById('chips-container').appendChild(chip); }
  chip.className = `chip ${cls}`;
  chip.innerHTML = `<span class="chip-grade">${esc(grade)}</span><span class="chip-name">${esc(truncName(name,20))}</span>`;
  updateLiveProgress();
}

function updateLiveProgress() {
  const pct = totalStudents > 0 ? (completedStudents / totalStudents * 100) : 0;
  document.getElementById('live-prog-fill').style.width = pct.toFixed(1) + '%';
  document.getElementById('live-prog-text').textContent =
    `${completedStudents} / ${totalStudents} estudiante${totalStudents !== 1 ? 's' : ''} calificado${totalStudents !== 1 ? 's' : ''}`;
}

function showResultsCard() {
  if (liveResults.length === 0) return;
  document.querySelectorAll('.filter-pill').forEach(p => p.classList.remove('active'));
  document.querySelectorAll('.sort-btn').forEach(b => b.classList.toggle('active', b.dataset.sort === 'apellido'));
  currentSort = 'apellido'; activeFilters = new Set();
  applyFiltersAndSort();
  const card = document.getElementById('results-card');
  card.classList.remove('hidden','fade-in'); void card.offsetWidth; card.classList.add('fade-in');
  setTimeout(() => card.scrollIntoView({ behavior:'smooth', block:'start' }), 140);
}

function sortResults(mode) {
  currentSort = mode;
  document.querySelectorAll('.sort-btn').forEach(b => b.classList.toggle('active', b.dataset.sort === mode));
  applyFiltersAndSort();
}

function toggleFilter(flag) {
  if (activeFilters.has(flag)) activeFilters.delete(flag); else activeFilters.add(flag);
  document.querySelectorAll('.filter-pill').forEach(p => p.classList.toggle('active', activeFilters.has(p.dataset.filter)));
  applyFiltersAndSort();
}

function normalizeForSearch(s) {
  return String(s || '').toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

function lastNameKey(fullName) {
  const parts = String(fullName || '').trim().split(/\s+/);
  return parts[parts.length - 1] || '';
}

function onStudentSearchInput(value) {
  studentSearchQuery = value.trim();
  document.getElementById('search-clear-btn').classList.toggle('hidden', !studentSearchQuery);
  applyFiltersAndSort();
}

function clearStudentSearch() {
  studentSearchQuery = '';
  const input = document.getElementById('student-search-input');
  input.value = '';
  document.getElementById('search-clear-btn').classList.add('hidden');
  applyFiltersAndSort();
  input.focus();
}

function applyFiltersAndSort() {
  let results = [...liveResults];
  if (activeFilters.has('plagio'))    results = results.filter(r => r.plagio);
  if (activeFilters.has('nocompila')) results = results.filter(r => r.compila && r.compila !== 'SI' && r.compila !== 'N/A');
  if (activeFilters.has('baja'))      results = results.filter(r => parseFloat(r.nota) < 3);
  if (studentSearchQuery) {
    const q = normalizeForSearch(studentSearchQuery);
    results = results.filter(r => normalizeForSearch(r.estudiante).includes(q));
  }
  if      (currentSort === 'apellido') results.sort((a,b) => lastNameKey(a.estudiante).localeCompare(lastNameKey(b.estudiante), 'es', { sensitivity: 'base' }) || String(a.estudiante).localeCompare(String(b.estudiante), 'es'));
  else if (currentSort === 'desc')     results.sort((a,b) => parseFloat(b.nota||0) - parseFloat(a.nota||0));
  else if (currentSort === 'asc')      results.sort((a,b) => parseFloat(a.nota||0) - parseFloat(b.nota||0));
  else if (currentSort === 'az')       results.sort((a,b) => String(a.estudiante).localeCompare(String(b.estudiante), 'es'));
  else if (currentSort === 'plagio')   results.sort((a,b) => (b.plagio?1:0) - (a.plagio?1:0));
  renderCardsFromResults(results);
}

function renderCardsFromResults(results) {
  _lastRendered = results;
  renderStatsRow(results);
  const grid = document.getElementById('students-grid');
  grid.innerHTML = '';
  _previewCodes = [];
  results.forEach((res, ri) => grid.appendChild(buildStudentCard(res, ri)));
}

function computeStats(results) {
  const count = results.length;
  let avgNota = '—';
  const vals = results.map(r => parseFloat(r.nota)).filter(n => !isNaN(n) && n >= 0);
  if (vals.length) avgNota = (vals.reduce((a,b)=>a+b,0)/vals.length).toFixed(1);
  const compileCount = results.filter(r => (r.compila||'') === 'SI').length;
  const plagioCount  = results.filter(r => (r.plagio ||'') !== '').length;
  return { count, avgNota, compileCount, plagioCount };
}

function renderStatsRow(results) {
  const { count, avgNota, compileCount, plagioCount } = computeStats(results);
  document.getElementById('results-count').textContent = `${count} estudiante${count!==1?'s':''}`;
  document.getElementById('stats-row').innerHTML = [
    { val: avgNota, label: 'Promedio', color: 'linear-gradient(135deg,var(--p1),var(--p3))' },
    { val: `${compileCount}/${count}`, label: 'Compilan', color: 'linear-gradient(135deg,#059669,var(--green))' },
    { val: plagioCount, label: 'Posible plagio', color: 'linear-gradient(135deg,#b91c1c,var(--red))' },
  ].map(s =>
    `<div class="stat-item">
      <div class="stat-value" style="background:${s.color};-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent">${s.val}</div>
      <div class="stat-label">${s.label}</div>
    </div>`
  ).join('');
}

function getInitials(name) {
  const p = String(name).trim().split(/\s+/);
  if (p.length >= 2) return (p[0][0] + p[p.length-1][0]).toUpperCase();
  return String(name).slice(0,2).toUpperCase();
}

function avatarColor(name) {
  const pal = ['#6366f1','#8b5cf6','#ec4899','#10b981','#f59e0b','#3b82f6','#ef4444','#14b8a6','#f97316','#06b6d4'];
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffffffff;
  return pal[Math.abs(h) % pal.length];
}

function esc(s) { return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function gradeColorClass(n) { if (isNaN(n)) return 'dim'; return n>=3.5?'hi':n>=2.5?'mid':'lo'; }
function gradeBarColor(n)   { return n>=3.5?'var(--green)':n>=2.5?'var(--yellow)':'var(--red)'; }

function buildStudentCard(res, ri) {
  const id         = res._id;
  const nameRaw    = res.estudiante || '—';
  const compilaRaw = res.compila    || '';
  const plagioRaw  = res.plagio     || '';
  const notaN      = parseFloat(res.nota);
  const comentario = res.comentario || '';
  const codigoRaw  = res.codigo     || '';
  const barW       = (!isNaN(notaN)&&notaN>=0) ? Math.min(100,(notaN/5)*100).toFixed(1) : 0;
  const notaCls    = gradeColorClass(notaN);
  const notaVal    = isNaN(notaN) ? '' : notaN.toFixed(1);
  const initials   = getInitials(nameRaw);
  const avColor    = avatarColor(nameRaw);

  let badges = '';
  if      (compilaRaw === 'SI')  badges += '<span class="stu-badge ok">Compila</span>';
  else if (compilaRaw && compilaRaw !== 'N/A') badges += '<span class="stu-badge warn">Error compilación</span>';
  else if (compilaRaw === 'N/A') badges += '<span class="stu-badge muted">N/A</span>';
  if (plagioRaw) badges += `<button class="stu-badge amber stu-badge-btn" onclick="openDiff(${id})" title="Ver comparación lado a lado">${esc(plagioRaw)}</button>`;

  const errHtml = (compilaRaw && compilaRaw !== 'SI' && compilaRaw !== 'N/A')
    ? `<div class="stu-error">${esc(compilaRaw.slice(0,600))}${compilaRaw.length>600?'\n…':''}</div>` : '';

  const codeIdx = _previewCodes.length;
  _previewCodes.push({ name: nameRaw, code: codigoRaw });
  const previewHtml = codigoRaw
    ? `<button class="stu-preview-btn" onclick="openCodePreview(${codeIdx})">
         <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>
         Ver código
       </button>` : '';

  const card = document.createElement('div');
  card.className = 'stu-card fade-in';
  card.dataset.id = id;
  card.style.animationDelay = Math.min(ri*35,500) + 'ms';
  card.innerHTML = `
    <div class="stu-card-main">
      <div class="stu-avatar" style="background:${avColor}">${esc(initials)}</div>
      <div class="stu-info">
        <div class="stu-name">${esc(nameRaw)}</div>
        <div class="stu-bar-wrap"><div class="stu-bar" id="bar-${id}" style="width:${barW}%;background:${isNaN(notaN)?'var(--text-3)':gradeBarColor(notaN)}"></div></div>
      </div>
      <div>
        <div class="stu-grade-big ${notaCls}" id="grade-wrap-${id}">
          <input type="number" class="stu-grade-edit" id="grade-input-${id}" min="0" max="5" step="0.1"
                 value="${notaVal}" aria-label="Nota de ${esc(nameRaw)}"
                 oninput="onGradeEdit(${id}, this.value)" onblur="onGradeBlur(${id}, this)" />
        </div>
        <div class="grade-edit-hint">de 5.0 · editable</div>
      </div>
    </div>
    ${badges ? `<div class="stu-badges">${badges}</div>` : ''}
    <div class="stu-comment-block">
      <div class="stu-comment-label">Evaluador · editable</div>
      <textarea class="stu-comment-edit" rows="2" placeholder="Sin comentario. Escribe uno para el estudiante…"
                aria-label="Comentario de ${esc(nameRaw)}"
                oninput="onCommentEdit(${id}, this.value)">${esc(comentario)}</textarea>
    </div>
    ${errHtml}
    <div class="stu-card-actions">
      <button class="stu-copy-btn" id="copy-${id}" onclick="copyStudent(${id})" title="Copiar nota (y comentario) para pegar en el Campus Virtual">
        <svg viewBox="0 0 16 16" fill="currentColor"><path d="M4 2a2 2 0 0 1 2-2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V2zm2-.5a.5.5 0 0 0-.5.5v8a.5.5 0 0 0 .5.5h6a.5.5 0 0 0 .5-.5V2a.5.5 0 0 0-.5-.5H6z"/><path d="M2 5a2 2 0 0 1 2-2v1.5A.5.5 0 0 0 3.5 5v9a.5.5 0 0 0 .5.5h6a.5.5 0 0 0 .5-.5H12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5z"/></svg>
        Copiar nota
      </button>
      ${previewHtml}
      <button class="ask-ai-btn" onclick="toggleAskAI(${id})" title="Consultar IA sobre el código">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
        Ask AI
      </button>
    </div>
    <div class="ask-ai-panel hidden" id="ask-ai-${id}">
      <div class="ask-ai-input-row">
        <textarea class="ask-ai-input" id="ask-ai-q-${id}" rows="2"
          placeholder="Pregunta algo sobre el código de este estudiante…"
          onkeydown="askAIKeydown(event,${id})"></textarea>
        <button class="ask-ai-send" id="ask-ai-send-${id}" onclick="submitAskAI(${id})">Enviar</button>
      </div>
      <div class="ask-ai-response hidden" id="ask-ai-r-${id}"></div>
    </div>`;
  return card;
}

// ── Edición en vivo de nota / comentario ──
function findResult(id) { return liveResults.find(r => r._id === id); }

function updateGradeVisual(id, nota) {
  const n = parseFloat(nota);
  const wrap = document.getElementById('grade-wrap-' + id);
  if (wrap) wrap.className = 'stu-grade-big ' + gradeColorClass(n);
  const bar = document.getElementById('bar-' + id);
  if (bar) {
    const w = (!isNaN(n) && n >= 0) ? Math.min(100, (n/5)*100).toFixed(1) : 0;
    bar.style.width = w + '%';
    bar.style.background = isNaN(n) ? 'var(--text-3)' : gradeBarColor(n);
  }
}

function onGradeEdit(id, val) {
  const res = findResult(id);
  if (!res) return;
  let n = parseFloat(val);
  if (isNaN(n)) { res.nota = ''; }
  else { n = Math.max(0, Math.min(5, n)); res.nota = n; }
  updateGradeVisual(id, res.nota);
  renderStatsRow(_lastRendered);
  scheduleSync();
}

function onGradeBlur(id, input) {
  const res = findResult(id);
  if (!res) return;
  const n = parseFloat(res.nota);
  input.value = isNaN(n) ? '' : n.toFixed(1);
}

function onCommentEdit(id, val) {
  const res = findResult(id);
  if (!res) return;
  res.comentario = val;
  scheduleSync();
}

async function copyStudent(id) {
  const res = findResult(id);
  if (!res) return;
  const n = parseFloat(res.nota);
  const nota = isNaN(n) ? '' : n.toFixed(1);
  const text = res.comentario ? `${nota}\t${res.comentario}` : nota;
  try {
    await navigator.clipboard.writeText(text);
    const btn = document.getElementById('copy-' + id);
    if (btn) {
      btn.classList.add('copied');
      const label = btn.lastChild;
      label.textContent = ' Copiado';
      setTimeout(() => { btn.classList.remove('copied'); label.textContent = ' Copiar nota'; }, 1800);
    }
  } catch (e) { console.warn('Copy failed:', e); }
}

function scheduleSync() {
  clearTimeout(_syncTimer);
  _syncTimer = setTimeout(syncResults, 700);
}

async function syncResults() {
  if (!currentJobId) return;
  try {
    await fetch(`/results/${currentJobId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(liveResults.map(r => ({
        estudiante: r.estudiante, compila: r.compila, plagio: r.plagio,
        nota: r.nota, comentario: r.comentario,
      }))),
    });
  } catch (e) { console.warn('Sync failed:', e); }
}

function lineClass(text) {
  if (!text) return 'blank';
  if (/^={3,}|^-{3,}/.test(text))                              return 'sep';
  if (/ACADEMIC PREGRADER|INICIO/.test(text))                  return 'section';
  if (/procesando:/i.test(text))                               return 'section';
  if (/error|falló|no se encontró|no se generó/i.test(text))  return 'err';
  if (/exitosa|correctamente|obtenido|completad|✓/i.test(text)) return 'ok';
  if (/advertencia|omitida|omitido/i.test(text))              return 'warn';
  return 'info';
}

function appendLog(text) {
  const log   = document.getElementById('log-output');
  const empty = log.querySelector('.log-empty');
  if (empty) empty.remove();
  const div = document.createElement('div');
  div.className = 'log-line ' + lineClass(text);
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function setStatusDot(state)    { document.getElementById('status-dot').className = 'status-dot ' + state; }
function setStatusText(t)       { document.getElementById('status-text').textContent = t; }
function setStatusBadge(t, cls) { const b = document.getElementById('status-badge'); b.textContent = t; b.className = 'status-badge ' + cls; }

function downloadCSV()   { if (currentJobId) flushAndDownload(`/download/${currentJobId}`); }
function downloadExcel() { if (currentJobId) flushAndDownload(`/download/${currentJobId}/excel`); }

async function flushAndDownload(url) {
  clearTimeout(_syncTimer);
  await syncResults();
  window.location.href = url;
}

function downloadCampus() {
  if (!currentJobId) return;
  const hint = document.getElementById('campus-course-hint');
  const picker = document.getElementById('course-picker');
  if (picker) {
    const name = picker.options[picker.selectedIndex]?.text || '';
    hint.textContent = picker.value ? `Curso activo: ${name}` : 'Elige primero un curso en la barra superior.';
  } else {
    hint.textContent = '';
  }
  document.getElementById('campus-feedback').classList.add('hidden');
  document.getElementById('campus-overlay').classList.remove('hidden');
  setTimeout(() => document.getElementById('campus-item').focus(), 50);
}

function closeDiff() { document.getElementById('diff-overlay').classList.add('hidden'); }
function closeDiffOutside(e) { if (e.target === document.getElementById('diff-overlay')) closeDiff(); }

function parsePlagioName(plagioRaw) {
  const m = (plagioRaw || '').match(/^Con:\s*(.+?)\s*\(\d/);
  return m ? m[1].trim() : null;
}

function openDiff(studentId) {
  const ra = liveResults.find(r => r._id === studentId);
  if (!ra) return;

  const otherName = parsePlagioName(ra.plagio || '');
  const rb = otherName ? liveResults.find(r => r.estudiante === otherName) : null;

  // similarity label
  const simMatch = (ra.plagio || '').match(/(\d+(?:\.\d+)?%)/);
  const simEl = document.getElementById('diff-sim-label');
  simEl.textContent = simMatch ? `Similitud: ${simMatch[1]}` : 'Posible plagio';

  function fillPane(nameEl, avEl, codeEl, res, fallbackName) {
    const name = res?.estudiante || fallbackName || '—';
    nameEl.textContent = name;
    avEl.textContent = getInitials(name);
    avEl.style.background = avatarColor(name);
    codeEl.classList.toggle('hljs', !!window.hljs);
    codeEl.innerHTML = res?.codigo
      ? highlightCodeFiles(res.codigo)
      : '<span class="code-empty">Código no disponible.</span>';
    codeEl.scrollTop = 0;
  }

  fillPane(
    document.getElementById('diff-name-a'), document.getElementById('diff-av-a'), document.getElementById('diff-code-a'),
    ra, ra.estudiante
  );
  fillPane(
    document.getElementById('diff-name-b'), document.getElementById('diff-av-b'), document.getElementById('diff-code-b'),
    rb, otherName
  );

  document.getElementById('diff-overlay').classList.remove('hidden');
}

function closeCampus() { document.getElementById('campus-overlay').classList.add('hidden'); }
function closeCampusOutside(e) { if (e.target === e.currentTarget) closeCampus(); }

async function confirmCampusDownload() {
  const item = document.getElementById('campus-item').value.trim();
  const fb = document.getElementById('campus-feedback');
  if (!item) { fb.textContent = 'Escribe el nombre del ítem.'; fb.classList.remove('hidden'); return; }
  const btn = document.getElementById('btn-campus-dl');
  btn.disabled = true;
  fb.classList.remove('hidden'); fb.textContent = 'Generando…';
  try {
    clearTimeout(_syncTimer);
    await syncResults();
    const res = await fetch(`/download/${currentJobId}/campus?item=${encodeURIComponent(item)}`);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      fb.textContent = err.error || 'No se pudo generar el archivo.';
      return;
    }
    const matched = res.headers.get('X-Matched-Count') || '0';
    const unmatchedN = parseInt(res.headers.get('X-Unmatched-Count') || '0', 10);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `campus_${item.replace(/[^A-Za-z0-9_-]+/g, '_') || 'notas'}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    if (unmatchedN > 0) {
      const names = decodeURIComponent(res.headers.get('X-Unmatched') || '');
      fb.textContent = `${matched} nota(s) exportada(s). ${unmatchedN} sin emparejar: ${names}`;
    } else {
      fb.textContent = `${matched} nota(s) exportada(s). Listo para importar.`;
      setTimeout(closeCampus, 1600);
    }
  } catch (e) {
    fb.textContent = 'Error: ' + e.message;
  } finally {
    btn.disabled = false;
  }
}

// ── Ask AI ──
function toggleExtraNotes() {
  const toggle = document.getElementById('extra-notes-toggle');
  const body   = document.getElementById('extra-notes-body');
  const isOpen = body.classList.toggle('open');
  toggle.classList.toggle('open', isOpen);
  if (isOpen) setTimeout(() => document.getElementById('extra-notes')?.focus(), 230);
}

function updateExtraNotesDot() {
  const toggle = document.getElementById('extra-notes-toggle');
  const val = document.getElementById('extra-notes')?.value || '';
  toggle?.classList.toggle('has-content', val.trim().length > 0);
}

function toggleAskAI(id) {
  const panel = document.getElementById('ask-ai-' + id);
  if (!panel) return;
  panel.classList.toggle('hidden');
  if (!panel.classList.contains('hidden')) {
    const inp = document.getElementById('ask-ai-q-' + id);
    if (inp) setTimeout(() => inp.focus(), 50);
  }
}

function askAIKeydown(e, id) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitAskAI(id); }
}

async function submitAskAI(id) {
  const qEl  = document.getElementById('ask-ai-q-' + id);
  const rEl  = document.getElementById('ask-ai-r-' + id);
  const send = document.getElementById('ask-ai-send-' + id);
  if (!qEl || !rEl) return;
  const question = qEl.value.trim();
  if (!question) return;

  // Get code for this card from _previewCodes via card dataset
  const card = qEl.closest('.stu-card');
  const cardId = card ? parseInt(card.dataset.id, 10) : -1;
  const result = liveResults.find(r => r._id === cardId);
  const code = result?.codigo || '';

  send.disabled = true;
  rEl.className = 'ask-ai-response loading';
  rEl.textContent = 'Consultando IA…';

  try {
    const res = await fetch('/ask_ai', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, question, job_id: currentJobId }),
    });
    const pl = await res.json();
    if (!res.ok || pl.error) {
      rEl.className = 'ask-ai-response error';
      rEl.textContent = pl.error || 'Error desconocido.';
    } else {
      rEl.className = 'ask-ai-response';
      rEl.textContent = pl.answer;
    }
  } catch (e) {
    rEl.className = 'ask-ai-response error';
    rEl.textContent = 'Error de red: ' + e.message;
  } finally {
    send.disabled = false;
  }
}

// ── Code preview ──
function detectLang(filename) {
  const ext = (filename.split('.').pop() || '').toLowerCase();
  const map = {
    py: 'python', js: 'javascript', ts: 'typescript', jsx: 'javascript', tsx: 'typescript',
    java: 'java', c: 'c', cpp: 'cpp', cc: 'cpp', h: 'c', hpp: 'cpp',
    cs: 'csharp', rb: 'ruby', go: 'go', rs: 'rust', php: 'php',
    swift: 'swift', kt: 'kotlin', scala: 'scala', r: 'r', m: 'matlab',
    html: 'xml', css: 'css', xml: 'xml', json: 'json', yaml: 'yaml', yml: 'yaml',
    sh: 'bash', sql: 'sql', pl: 'perl',
  };
  return map[ext] || 'plaintext';
}

function highlightCodeFiles(code) {
  const parts = code.split(/^(\/\/ --- .* ---)$/gm);
  let html = '';
  let lang = 'plaintext';
  for (const part of parts) {
    const m = part.match(/^\/\/ --- (.*) ---$/);
    if (m) {
      lang = detectLang(m[1].trim());
      html += `<span class="code-file">${esc(part)}</span>`;
    } else if (part) {
      html += window.hljs
        ? hljs.highlight(part, { language: lang, ignoreIllegals: true }).value
        : esc(part);
    }
  }
  return html;
}

let _currentPreviewIdx = -1;
const RUNNABLE_LANGS = new Set(['python', 'cpp', 'c', 'java']);
// Estado de la consola interactiva actualmente abierta (si la hay).
let _consoleRunId = null;
let _consoleSource = null;

function detectRunnableLang(code) {
  // Usa el primer marcador "// --- archivo ---" para inferir el lenguaje ejecutable.
  const m = (code || '').match(/^\/\/ --- (.*) ---$/m);
  const lang = m ? detectLang(m[1].trim()) : 'plaintext';
  return lang === 'c' ? 'cpp' : lang;
}

function openCodePreview(idx) {
  const item = _previewCodes[idx];
  if (!item) return;
  stopConsoleSession(); // por si quedó una consola corriendo de una entrega anterior
  _currentPreviewIdx = idx;
  document.getElementById('code-modal-name').textContent = item.name || 'Código';
  const lines = item.code ? item.code.split('\n').length : 0;
  const chars = item.code ? item.code.length : 0;
  document.getElementById('code-modal-meta').textContent =
    item.code ? `${lines} línea${lines !== 1 ? 's' : ''} · ${chars} caracteres` : '';
  const body = document.getElementById('code-modal-body');
  body.classList.toggle('hljs', !!window.hljs);
  body.innerHTML = item.code
    ? highlightCodeFiles(item.code)
    : '<span class="code-empty">No hay código disponible para esta entrega.</span>';
  body.scrollTop = 0;
  resetCopyBtn();

  // Reset del panel de ejecución
  const lang = detectRunnableLang(item.code);
  const runToolbar = document.getElementById('run-toolbar');
  const langBadge = document.getElementById('run-lang-badge');
  const runnable = !!item.code && RUNNABLE_LANGS.has(lang);
  runToolbar.classList.toggle('hidden', !runnable);
  langBadge.classList.toggle('hidden', !runnable);
  langBadge.textContent = lang === 'cpp' ? 'C++' : lang === 'java' ? 'Java' : lang === 'python' ? 'Python' : lang;
  document.getElementById('console-panel').classList.add('hidden');
  document.getElementById('stop-code-btn').classList.add('hidden');
  setConsoleInputEnabled(false);
  const runBtn = document.getElementById('run-code-btn');
  runBtn.disabled = false;
  runBtn.classList.remove('hidden');
  runBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg> Ejecutar';

  document.getElementById('code-overlay').classList.remove('hidden');
}

function setConsoleInputEnabled(enabled) {
  document.getElementById('console-input').disabled = !enabled;
  document.getElementById('console-send-btn').disabled = !enabled;
  if (enabled) document.getElementById('console-input').focus();
}

function appendConsoleOutput(text) {
  const outEl = document.getElementById('console-out');
  const empty = outEl.querySelector('.console-empty');
  if (empty) outEl.textContent = '';
  outEl.appendChild(document.createTextNode(text));
  outEl.scrollTop = outEl.scrollHeight;
}

async function runPreviewCode() {
  const item = _previewCodes[_currentPreviewIdx];
  if (!item || !item.code) return;
  const runBtn = document.getElementById('run-code-btn');
  const stopBtn = document.getElementById('stop-code-btn');
  const panel = document.getElementById('console-panel');
  const statusEl = document.getElementById('console-status');
  const metaEl = document.getElementById('console-meta');
  const outEl = document.getElementById('console-out');

  runBtn.classList.add('hidden');
  stopBtn.classList.remove('hidden');
  panel.classList.remove('hidden');
  statusEl.classList.remove('hidden');
  statusEl.className = 'console-status running';
  statusEl.textContent = '● Ejecutando…';
  metaEl.textContent = '';
  outEl.innerHTML = '<span class="console-empty">Compilando…</span>';
  setConsoleInputEnabled(false);

  try {
    const res = await fetch('/run_code/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: item.code }),
    });
    const pl = await res.json();
    if (!res.ok || !pl.ok) {
      finishConsole(false, pl);
      return;
    }
    _consoleRunId = pl.run_id;
    outEl.innerHTML = '';
    setConsoleInputEnabled(true);
    openConsoleStream(pl.run_id);
  } catch (e) {
    statusEl.className = 'console-status error';
    statusEl.textContent = '✕ Error';
    outEl.innerHTML = `<span class="stderr-line">Error de red: ${esc(e.message)}</span>`;
    resetRunButtons();
  }
}

function openConsoleStream(runId) {
  if (_consoleSource) _consoleSource.close();
  const es = new EventSource(`/run_code/stream/${runId}`);
  _consoleSource = es;
  es.onmessage = (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch { return; }
    if (msg.type === 'output') {
      appendConsoleOutput(msg.data);
    } else if (msg.type === 'done') {
      finishConsole(true, msg);
    } else if (msg.type === 'error') {
      appendConsoleOutput('\n[' + (msg.data || 'Error') + ']');
      finishConsole(false, {});
    }
  };
  es.onerror = () => {
    // Conexión caída sin evento "done" explícito (p.ej. red/servidor reiniciado).
    if (_consoleRunId === runId) finishConsole(false, { error: 'Se perdió la conexión con la consola.' });
  };
}

function finishConsole(ranOk, pl) {
  if (_consoleSource) { _consoleSource.close(); _consoleSource = null; }
  _consoleRunId = null;
  setConsoleInputEnabled(false);
  resetRunButtons();

  const statusEl = document.getElementById('console-status');
  const metaEl = document.getElementById('console-meta');
  const outEl = document.getElementById('console-out');

  if (pl && pl.error) {
    statusEl.className = 'console-status error';
    statusEl.textContent = '✕ Error';
    if (!outEl.textContent.trim()) outEl.innerHTML = `<span class="stderr-line">${esc(pl.error)}</span>`;
    return;
  }
  if (pl && pl.stage === 'compile') {
    statusEl.className = 'console-status error';
    statusEl.textContent = '✕ Error de compilación';
    let html = '';
    if (pl.stdout) html += esc(pl.stdout);
    if (pl.stderr) html += (html ? '\n' : '') + `<span class="stderr-line">${esc(pl.stderr)}</span>`;
    outEl.innerHTML = html || '<span class="console-empty">(sin salida)</span>';
    return;
  }

  const ok = pl && pl.exit_code === 0 && !pl.timed_out;
  statusEl.className = 'console-status ' + (ok ? 'ok' : 'error');
  statusEl.textContent = (ok ? '✓ Terminó' : '✕ Terminó con error');
  const metaParts = [];
  if (pl && pl.duration_ms != null) metaParts.push(`${pl.duration_ms} ms`);
  if (pl && pl.exit_code != null) metaParts.push(`exit code ${pl.exit_code}`);
  if (pl && pl.timed_out) metaParts.push('tiempo agotado');
  metaEl.textContent = metaParts.join(' · ');
  if (!outEl.textContent.trim() && !outEl.querySelector('.console-empty')) {
    outEl.innerHTML = '<span class="console-empty">(sin salida)</span>';
  }
}

function resetRunButtons() {
  const runBtn = document.getElementById('run-code-btn');
  const stopBtn = document.getElementById('stop-code-btn');
  stopBtn.classList.add('hidden');
  runBtn.classList.remove('hidden');
  runBtn.disabled = false;
  runBtn.innerHTML = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5v14l11-7z"/></svg> Ejecutar de nuevo';
}

function sendConsoleInput() {
  const input = document.getElementById('console-input');
  const text = input.value;
  if (!_consoleRunId) return;
  fetch(`/run_code/input/${_consoleRunId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ text }),
  }).catch(() => {});
  input.value = '';
  input.focus();
}

function stopPreviewCode() { stopConsoleSession(); }

function stopConsoleSession() {
  if (!_consoleRunId) return;
  const runId = _consoleRunId;
  fetch(`/run_code/stop/${runId}`, { method: 'POST' }).catch(() => {});
}

function closeCodePreview() {
  stopConsoleSession();
  if (_consoleSource) { _consoleSource.close(); _consoleSource = null; }
  _consoleRunId = null;
  document.getElementById('code-overlay').classList.add('hidden');
}
function closeCodePreviewOutside(e) { if (e.target === document.getElementById('code-overlay')) closeCodePreview(); }

function resetCopyBtn() {
  const btn = document.getElementById('code-copy-btn');
  btn.classList.remove('copied');
  btn.lastChild.textContent = ' Copiar';
}

async function copyPreviewCode() {
  const text = document.getElementById('code-modal-body').textContent || '';
  if (!text) return;
  const btn = document.getElementById('code-copy-btn');
  try {
    await navigator.clipboard.writeText(text);
    btn.classList.add('copied');
    btn.lastChild.textContent = ' Copiado';
    setTimeout(resetCopyBtn, 2000);
  } catch (e) { console.warn('Copy failed:', e); }
}
