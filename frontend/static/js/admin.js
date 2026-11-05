function showAdminSection(sectionName, updateHash = true) {
  const target = document.getElementById(`section-${sectionName}`);
  if (!target) return;

  document.querySelectorAll(".admin-section").forEach(section => {
    const active = section === target;
    section.classList.toggle("active", active);
    section.hidden = !active;
  });
  document.querySelectorAll(".admin-nav button").forEach(button => {
    const active = button.dataset.section === sectionName;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  if (updateHash) history.replaceState(null, "", `#${sectionName}`);
}

document.querySelectorAll(".admin-nav button").forEach(button => {
  button.addEventListener("click", () => showAdminSection(button.dataset.section));
});

function toggleTheme() {
  const cur = document.documentElement.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
  const next = cur === 'light' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('theme', next); } catch (e) {}
}

const EVENT_LABELS = {
  login: "Inició sesión", logout: "Cerró sesión", login_failed: "Login fallido",
  login_blocked: "Login bloqueado", grade_run: "Calificó", download_csv: "Descargó CSV",
  download_excel: "Descargó Excel", password_changed: "Cambió su clave",
  admin_create_user: "Creó usuario", admin_block: "Bloqueó", admin_unblock: "Desbloqueó",
  admin_reset_password: "Reinició clave", admin_set_role: "Cambió rol", admin_delete_user: "Eliminó usuario",
  admin_create_course: "Creó curso", admin_delete_course: "Eliminó curso",
  admin_update_course_students: "Actualizó roster", admin_assign_course: "Asignó curso",
  admin_set_course_type: "Asignó tipo de curso", admin_download_course_excel: "Descargó Excel de curso",
  download_campus: "Descargó Campus", admin_clear_events: "Limpió actividad",
};

const COURSE_TYPE_LABELS = {
  ip: "Introducción a la Programación",
  pa: "Programación Avanzada",
  fpia: "Fundamentos de Programación IA",
};

function toast(html, ms = 9000) {
  const t = document.getElementById("toast");
  t.innerHTML = html; t.style.display = "block";
  clearTimeout(t._timer); t._timer = setTimeout(() => t.style.display = "none", ms);
}

async function api(url, opts) {
  const r = await fetch(url, { headers: { "Content-Type": "application/json" }, ...opts });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || "Error");
  return data;
}

let _courses = [];
let _events = [];
let _allUsers = [];
let _firstLoad = true;

async function load() {
  try {
    const data = await api("/admin/api/overview");
    _courses = data.courses || [];
    _events = data.events || [];
    _allUsers = data.users || [];
    renderStats(data);
    renderInsights(data);
    renderActivityChart(_events);
    renderCourses(_courses);
    renderUsers();
    populateEventFilter(_allUsers);
    renderEvents();
  } catch (e) {
    if (_firstLoad) toast("Error al cargar el panel: " + esc(e.message));
  } finally {
    if (_firstLoad) {
      document.getElementById("loadingOverlay").classList.add("hide");
      _firstLoad = false;
    }
  }
}

async function loadGlobalConfig() {
  try {
    const c = await api("/admin/api/config");
    document.getElementById("gm-status").textContent = c.gemini_has_api_key ? "· configurada ✓" : "· no configurada";
    document.getElementById("oa-status").textContent = c.openai_has_api_key ? "· configurada ✓" : "· no configurada";
    document.getElementById("cfgGeminiEnabled").checked = c.gemini_enabled ?? true;
    document.getElementById("cfgOpenaiEnabled").checked = c.openai_enabled ?? true;
    document.getElementById("cfgAzureEnabled").checked = c.azure_openai_enabled ?? false;
    document.getElementById("cfgAzureEndpoint").value = c.azure_openai_endpoint || "";
    document.getElementById("cfgAzureDeployment").value = c.azure_openai_deployment || "";
    document.getElementById("cfgAzureApiVersion").value = c.azure_openai_api_version || "2024-10-21";
    document.getElementById("cfgJplag").value     = c.jplag_jar   || "";
    document.getElementById("cfgWorkers").value   = c.max_workers ?? 4;
    document.getElementById("cfgCampusExport").checked = c.campus_export_enabled ?? false;
    document.getElementById("cfgSysInstr").value  = c.system_instruction || "";
    document.getElementById("cfgEvalRules").value = c.eval_rules || "";
  } catch (e) { console.warn("Config load failed:", e); }
}

async function saveGlobalConfig() {
  const payload = {
    gemini_api_key:     document.getElementById("cfgGemini").value.trim(),
    openai_api_key:     document.getElementById("cfgOpenai").value.trim(),
    gemini_enabled:     document.getElementById("cfgGeminiEnabled").checked,
    openai_enabled:     document.getElementById("cfgOpenaiEnabled").checked,
    azure_openai_enabled: document.getElementById("cfgAzureEnabled").checked,
    azure_openai_endpoint: document.getElementById("cfgAzureEndpoint").value.trim(),
    azure_openai_deployment: document.getElementById("cfgAzureDeployment").value.trim(),
    azure_openai_api_version: document.getElementById("cfgAzureApiVersion").value.trim(),
    jplag_jar:          document.getElementById("cfgJplag").value.trim(),
    max_workers:        parseInt(document.getElementById("cfgWorkers").value) || 4,
    campus_export_enabled: document.getElementById("cfgCampusExport").checked,
    system_instruction: document.getElementById("cfgSysInstr").value.trim(),
    eval_rules:         document.getElementById("cfgEvalRules").value.trim(),
  };
  try {
    await api("/admin/api/config", { method: "POST", body: JSON.stringify(payload) });
    document.getElementById("cfgGemini").value = "";
    document.getElementById("cfgOpenai").value = "";
    const s = document.getElementById("cfgSaved");
    s.style.display = "inline"; setTimeout(() => s.style.display = "none", 3000);
    loadGlobalConfig();
  } catch (e) { toast("Error al guardar: " + esc(e.message)); }
}

function renderStats(data) {
  const users = data.users || [];
  const courses = data.courses || [];
  const events = data.events || [];
  const totalGrades    = users.reduce((a, u) => a + u.grade_count, 0);
  const totalDownloads = users.reduce((a, u) => a + u.download_count, 0);
  const blocked        = users.filter(u => u.is_blocked).length;
  const activeGraders  = users.filter(u => u.course_id).length;
  const totalStudents  = courses.reduce((a, c) => a + (c.student_count || 0), 0);
  const failedLogins   = events.filter(e => e.event_type === "login_failed").length;
  const avgGrades      = users.length ? (totalGrades / users.length).toFixed(1) : "0";
  const el = document.getElementById("stats");
  const cards = [
    ["Usuarios", users.length],
    ["Calificadores con curso", activeGraders],
    ["Cursos", courses.length],
    ["Estudiantes en cursos", totalStudents],
    ["Calificaciones", totalGrades],
    ["Prom. calif./usuario", avgGrades],
    ["Descargas", totalDownloads],
    ["Logins fallidos", failedLogins],
    ["Bloqueados", blocked],
  ];
  el.innerHTML = cards.map(([l, n]) => `<div class="stat"><div class="n">${n}</div><div class="l">${l}</div></div>`).join("");
}

// ── Insights derivados de los datos existentes (sin nuevas consultas al backend) ──
function renderInsights(data) {
  const users = data.users || [];
  const courses = data.courses || [];
  const events = data.events || [];
  const el = document.getElementById("insights");
  if (!el) return;

  const now = Date.now();
  const eventDates = events.map(e => ({ e, d: parseUtcTimestamp(e.ts) })).filter(x => x.d);
  const within = (ms) => new Set(eventDates.filter(x => now - x.d.getTime() <= ms).map(x => x.e.username || "")).size;
  const active24h = within(24 * 3600 * 1000);
  const active7d  = within(7 * 24 * 3600 * 1000);

  const newUsers30d = users.filter(u => {
    const d = parseUtcTimestamp(u.created_at);
    return d && (now - d.getTime()) <= 30 * 24 * 3600 * 1000;
  }).length;

  const topGrader = users.reduce((best, u) => (u.grade_count > (best?.grade_count || 0) ? u : best), null);
  const topCourse = courses.reduce((best, c) => ((c.student_count || 0) > (best?.student_count || 0) ? c : best), null);
  const blockedPct = users.length ? Math.round(users.filter(u => u.is_blocked).length / users.length * 100) : 0;

  const cards = [
    [`${active24h}`, "Usuarios activos (24 h)"],
    [`${active7d}`, "Usuarios activos (7 días)"],
    [`${newUsers30d}`, "Cuentas nuevas (30 días)"],
    [topGrader && topGrader.grade_count ? `${esc(topGrader.username)} <small>(${topGrader.grade_count})</small>` : "—", "Calificador más activo"],
    [topCourse && topCourse.student_count ? `${esc(topCourse.name)} <small>(${topCourse.student_count})</small>` : "—", "Curso más numeroso"],
    [`${blockedPct}%`, "Usuarios bloqueados"],
  ];
  el.innerHTML = cards.map(([n, l]) => `<div class="insight-card"><div class="n">${n}</div><div class="l">${l}</div></div>`).join("");
}

function renderActivityChart(events) {
  const el = document.getElementById("activityChart");
  if (!el) return;
  const days = [];
  for (let i = 6; i >= 0; i--) {
    const d = new Date(Date.now() - i * 24 * 3600 * 1000);
    days.push({ key: BOGOTA_DAY_FMT.format(d), label: BOGOTA_WEEKDAY_FMT.format(d), count: 0 });
  }
  const byKey = Object.fromEntries(days.map(d => [d.key, d]));
  events.forEach(e => {
    const d = parseUtcTimestamp(e.ts);
    if (!d) return;
    const key = BOGOTA_DAY_FMT.format(d);
    if (byKey[key]) byKey[key].count++;
  });
  const max = Math.max(1, ...days.map(d => d.count));
  el.innerHTML = days.map(d => `
    <div class="bar-col" title="${d.count} evento(s)">
      <div class="bar" style="height:${Math.max(4, Math.round(d.count / max * 100))}%"></div>
      <span class="bar-day">${d.label}</span>
    </div>`).join("");
}

function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }

// ── Fecha/hora del último acceso: normaliza a UTC-5 (Bogotá) + "hace X" ──
function parseUtcTimestamp(raw) {
  if (!raw) return null;
  let s = String(raw).trim();
  // Ya trae zona horaria (ISO con Z/offset o RFC de Postgres) -> Date la interpreta bien.
  if (/[zZ]$|[+-]\d{2}:?\d{2}$|GMT$/.test(s)) {
    const d = new Date(s);
    return isNaN(d) ? null : d;
  }
  // "YYYY-MM-DD HH:MM:SS[.ffffff]" sin zona (SQLite/Postgres naive) -> es UTC.
  const d = new Date(s.replace(" ", "T") + "Z");
  return isNaN(d) ? null : d;
}

const BOGOTA_FMT = new Intl.DateTimeFormat("es-CO", {
  timeZone: "America/Bogota", day: "2-digit", month: "2-digit", year: "numeric",
  hour: "2-digit", minute: "2-digit", hour12: false,
});
const BOGOTA_DAY_FMT = new Intl.DateTimeFormat("en-CA", { timeZone: "America/Bogota", year: "numeric", month: "2-digit", day: "2-digit" });
const BOGOTA_WEEKDAY_FMT = new Intl.DateTimeFormat("es-CO", { timeZone: "America/Bogota", weekday: "short" });

function relativeTimeEs(date) {
  const diffSec = Math.round((Date.now() - date.getTime()) / 1000);
  if (diffSec < 45) return "hace instantes";
  const diffMin = Math.round(diffSec / 60);
  if (diffMin < 60) return `hace ${diffMin} min`;
  const diffH = Math.round(diffMin / 60);
  if (diffH < 24) return `hace ${diffH} h`;
  const diffD = Math.round(diffH / 24);
  if (diffD < 30) return `hace ${diffD} d`;
  const diffMonth = Math.round(diffD / 30);
  if (diffMonth < 12) return `hace ${diffMonth} mes${diffMonth > 1 ? "es" : ""}`;
  const diffY = Math.round(diffMonth / 12);
  return `hace ${diffY} año${diffY > 1 ? "s" : ""}`;
}

function formatDateTime(raw, emptyLabel = "nunca") {
  const d = parseUtcTimestamp(raw);
  if (!d) return `<div class="dt-cell"><span class="muted">${emptyLabel}</span></div>`;
  const abs = BOGOTA_FMT.format(d).replace(",", "");
  return `<div class="dt-cell"><span class="dt-rel" title="${abs} (UTC-5)">${relativeTimeEs(d)}</span><span class="dt-abs mono">${abs}</span></div>`;
}

const AVATAR_COLORS = ["#5a67d6", "#0e9f6e", "#c2410c", "#0891b2", "#a21caf", "#b45309", "#be123c", "#4338ca"];
function avatarColor(name) {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) >>> 0;
  return AVATAR_COLORS[h % AVATAR_COLORS.length];
}

// ── Menú de acciones por fila (kebab): evita botones apilados que forzaban scroll horizontal ──
const MENU_ICON = '<svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor"><circle cx="12" cy="5" r="1.7"/><circle cx="12" cy="12" r="1.7"/><circle cx="12" cy="19" r="1.7"/></svg>';
function rowMenu(id, label, itemsHtml) {
  return `<div class="row-menu">
    <button type="button" class="btn btn-sm menu-trigger" onclick="toggleRowMenu(event, '${id}')" aria-haspopup="true" aria-label="Acciones para ${label}">${MENU_ICON}</button>
    <div class="row-menu-list" id="${id}" hidden>${itemsHtml}</div>
  </div>`;
}
function closeAllRowMenus() { document.querySelectorAll(".row-menu-list").forEach(m => m.hidden = true); }
function toggleRowMenu(evt, id) {
  evt.stopPropagation();
  const menu = document.getElementById(id);
  if (!menu) return;
  const opening = menu.hidden;
  closeAllRowMenus();
  if (!opening) return;
  const rect = evt.currentTarget.getBoundingClientRect();
  menu.style.top = Math.min(rect.bottom + 4, window.innerHeight - 10) + "px";
  menu.style.right = Math.max(window.innerWidth - rect.right, 8) + "px";
  menu.hidden = false;
}
document.addEventListener("click", closeAllRowMenus);
document.addEventListener("keydown", e => { if (e.key === "Escape") closeAllRowMenus(); });
window.addEventListener("scroll", closeAllRowMenus, true);
window.addEventListener("resize", closeAllRowMenus);

function renderUsers() {
  const tb = document.querySelector("#usersTable tbody");
  const q = (document.getElementById("userSearch")?.value || "").trim().toLowerCase();
  const users = q ? _allUsers.filter(u => u.username.toLowerCase().includes(q)) : _allUsers;
  const countEl = document.getElementById("userSearchCount");
  if (countEl) countEl.textContent = q ? `${users.length} de ${_allUsers.length} usuario(s)` : `${_allUsers.length} usuario(s)`;
  if (!users.length) {
    tb.innerHTML = '<tr><td colspan="7" class="muted" style="text-align:center;padding:22px;">Ningún usuario coincide con la búsqueda.</td></tr>';
    return;
  }
  const courseOptions = (selected) => {
    const none = `<option value=""${!selected ? ' selected' : ''}>— sin curso —</option>`;
    const opts = _courses.map(c => `<option value="${c.id}"${c.id === selected ? ' selected' : ''}>${esc(c.name)}</option>`).join("");
    return none + opts;
  };
  tb.innerHTML = users.map(u => {
    const role = u.is_admin ? '<span class="badge admin">admin</span>' : '<span class="muted">usuario</span>';
    const state = u.is_blocked ? '<span class="badge blocked">bloqueado</span>' : '<span class="badge ok">activo</span>';
    const un = esc(u.username);
    const courseSel = `<select class="course-select" onchange="assignCourse('${un}', this.value)">${courseOptions(u.course_id)}</select>`;
    const menu = rowMenu(`um-${un}`, un, `
        <button onclick="resetPwd('${un}')">Reiniciar clave</button>
        <button onclick="toggleBlock('${un}', ${u.is_blocked ? 'false' : 'true'})">${u.is_blocked ? 'Desbloquear' : 'Bloquear'}</button>
        <button onclick="toggleAdmin('${un}', ${u.is_admin ? 'false' : 'true'})">${u.is_admin ? 'Quitar admin' : 'Hacer admin'}</button>
        <hr />
        <button class="danger" onclick="delUser('${un}')">Eliminar usuario</button>`);
    return `<tr>
      <td data-label="Usuario"><div class="user-cell">
        <span class="avatar" style="background:${avatarColor(un)}">${esc(un.charAt(0).toUpperCase())}</span>
        <span class="user-name-wrap"><strong>${un}</strong>${u.must_change_password ? '<span class="temp-pw">clave temporal</span>' : ''}</span>
      </div></td>
      <td data-label="Rol">${role}</td>
      <td data-label="Estado">${state}</td>
      <td data-label="Curso activo">${courseSel}</td>
      <td data-label="Última actividad">${formatDateTime(u.last_activity)}</td>
      <td data-label="Actividad"><div class="stat-trio">
        <span class="stat-chip" title="Accesos totales"><strong>${u.login_count}</strong><small>accesos</small></span>
        <span class="stat-chip" title="Entregas calificadas"><strong>${u.grade_count}</strong><small>calificó</small></span>
        <span class="stat-chip" title="Descargas"><strong>${u.download_count}</strong><small>descargas</small></span>
      </div></td>
      <td data-label="Acciones">${menu}</td>
    </tr>`;
  }).join("");
}

function renderCourses(courses) {
  const tb = document.querySelector("#coursesTable tbody");
  if (!courses.length) {
    tb.innerHTML = '<tr><td colspan="6" class="muted" style="text-align:center;padding:22px;">Aún no hay cursos. Crea uno pegando la lista de clase.</td></tr>';
    return;
  }
  const typeOptions = (selected) => {
    const opts = Object.entries(COURSE_TYPE_LABELS)
      .map(([v, label]) => `<option value="${v}"${v === selected ? ' selected' : ''}>${esc(label)}</option>`)
      .join("");
    return `<option value=""${!selected ? ' selected disabled' : ''}>— asignar tipo —</option>` + opts;
  };
  tb.innerHTML = courses.map(c => {
    const graders = (c.graders && c.graders.length)
      ? c.graders.map(g => `<span class="badge admin">${esc(g)}</span>`).join(" ")
      : '<span class="muted">nadie asignado</span>';
    const escName = esc(c.name).replace(/'/g, "\\'");
    const typeCell = c.course_type
      ? `<select class="course-select" onchange="assignCourseType(${c.id}, this.value)">${typeOptions(c.course_type)}</select>`
      : `<select class="course-select" onchange="assignCourseType(${c.id}, this.value)">${typeOptions(null)}</select>`;
    const excelBtn = c.course_type
      ? `<a href="/admin/api/courses/${c.id}/excel" download>Descargar Excel</a>`
      : `<span style="opacity:.5;cursor:not-allowed;" title="Asigna primero el tipo de curso para poder generar el Excel.">Descargar Excel</span>`;
    const menu = rowMenu(`cm-${c.id}`, esc(c.name), `
        <button onclick="viewCourseStudents(${c.id}, '${escName}')">Ver estudiantes</button>
        ${excelBtn}
        <button class="danger" onclick="deleteCourse(${c.id}, '${escName}')">Eliminar curso</button>`);
    return `<tr>
      <td data-label="Curso"><strong>${esc(c.name)}</strong></td>
      <td data-label="Tipo">${typeCell}</td>
      <td data-label="Estudiantes">${c.student_count}</td>
      <td data-label="Calificadores"><div class="actions">${graders}</div></td>
      <td data-label="Creado">${formatDateTime(c.created_at, "—")}</td>
      <td data-label="Acciones">${menu}</td>
    </tr>`;
  }).join("");
}

async function previewClassList() {
  const class_list = document.getElementById("newCourseList").value;
  const info = document.getElementById("coursePreviewInfo");
  if (!class_list.trim()) { info.textContent = "Pega primero la lista de clase."; return; }
  try {
    const r = await api("/admin/api/courses/preview", { method: "POST", body: JSON.stringify({ class_list }) });
    const wrap = document.getElementById("coursePreviewWrap");
    const tb = document.querySelector("#coursePreviewTable tbody");
    tb.innerHTML = r.students.map(s => `<tr>
      <td>${esc(s.name)}</td><td class="mono">${esc(s.username)}</td><td class="mono">${esc(s.org_id)}</td>
    </tr>`).join("");
    wrap.style.display = r.count ? "block" : "none";
    info.textContent = `${r.count} estudiante(s) detectado(s).`;
  } catch (e) { info.textContent = "Error: " + e.message; }
}

async function createCourse() {
  const name = document.getElementById("newCourseName").value.trim();
  const class_list = document.getElementById("newCourseList").value;
  const course_type = document.getElementById("newCourseType").value;
  if (!name) { toast("Escribe el nombre del curso."); return; }
  if (!course_type) { toast("Selecciona el tipo de curso."); return; }
  try {
    const r = await api("/admin/api/courses", { method: "POST", body: JSON.stringify({ name, class_list, course_type }) });
    document.getElementById("newCourseName").value = "";
    document.getElementById("newCourseList").value = "";
    document.getElementById("newCourseType").value = "";
    document.getElementById("coursePreviewWrap").style.display = "none";
    document.getElementById("coursePreviewInfo").textContent = "";
    toast(`Curso <strong>${esc(name)}</strong> creado con ${r.count} estudiante(s).`);
    load();
  } catch (e) { toast("Error: " + esc(e.message)); }
}

async function assignCourseType(course_id, course_type) {
  if (!course_type) return;
  try {
    await api(`/admin/api/courses/${course_id}/type`, {
      method: "POST", body: JSON.stringify({ course_type })
    });
    load();
  } catch (e) { toast("Error: " + esc(e.message)); load(); }
}

async function deleteCourse(id, name) {
  if (!confirm(`¿Eliminar el curso "${name}"? Se quitará de los calificadores asignados.`)) return;
  try { await api(`/admin/api/courses/${id}`, { method: "DELETE" }); load(); }
  catch (e) { toast("Error: " + esc(e.message)); }
}

async function viewCourseStudents(id, name) {
  closeAllRowMenus();
  const modal = document.getElementById("studentsModal");
  const tb = document.querySelector("#studentsModalTable tbody");
  document.getElementById("studentsModalTitle").textContent = `Estudiantes · ${name}`;
  tb.innerHTML = '<tr><td colspan="3" class="muted" style="text-align:center;padding:16px;">Cargando…</td></tr>';
  modal.classList.add("show");
  try {
    const r = await api(`/admin/api/courses/${id}/students`);
    const students = r.students || [];
    tb.innerHTML = students.length
      ? students.map(s => `<tr>
          <td>${esc(s.full_name || "")}</td>
          <td class="mono">${esc(s.org_id || "")}</td>
          <td class="mono">${esc(s.campus_username || "")}</td>
        </tr>`).join("")
      : '<tr><td colspan="3" class="muted" style="text-align:center;padding:16px;">Este curso no tiene estudiantes registrados.</td></tr>';
  } catch (e) {
    tb.innerHTML = `<tr><td colspan="3" class="muted" style="text-align:center;padding:16px;">Error: ${esc(e.message)}</td></tr>`;
  }
}

function closeStudentsModal() {
  document.getElementById("studentsModal").classList.remove("show");
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") closeStudentsModal();
});

async function assignCourse(username, course_id) {
  try {
    await api(`/admin/api/users/${encodeURIComponent(username)}/course`, {
      method: "POST", body: JSON.stringify({ course_id })
    });
    load();
  } catch (e) { toast("Error: " + esc(e.message)); load(); }
}

function populateEventFilter(users) {
  const sel = document.getElementById("eventUserFilter");
  const cur = sel.value;
  const names = users.map(u => u.username).sort();
  sel.innerHTML = '<option value="">Todos</option>' +
    names.map(n => `<option value="${esc(n)}">${esc(n)}</option>`).join("");
  if (names.includes(cur)) sel.value = cur;
}

async function clearGradeDownloadEvents() {
  if (!confirm("¿Borrar todos los eventos de calificaciones y descargas? Esto reinicia esos contadores y no se puede deshacer.")) return;
  try {
    const r = await api("/admin/api/events/clear", { method: "POST" });
    toast(`Se borraron ${r.deleted} evento(s) de calificaciones y descargas.`);
    load();
  } catch (e) { toast("Error: " + esc(e.message)); }
}

function renderEvents(events) {
  if (events) _events = events;
  const filter = document.getElementById("eventUserFilter").value;
  const rows = filter ? _events.filter(e => (e.username || "") === filter) : _events;
  const tb = document.querySelector("#eventsTable tbody");
  const count = document.getElementById("eventCount");
  if (count) count.textContent = `${rows.length} evento(s)`;
  if (!rows.length) {
    tb.innerHTML = '<tr><td colspan="5" class="muted" style="text-align:center;padding:22px;">Sin eventos para este filtro.</td></tr>';
    return;
  }
  tb.innerHTML = rows.map(e => {
    const rowClass = e.event_type === "login_failed" || e.event_type === "login_blocked" ? "evt-fail"
      : e.event_type === "grade_run" ? "evt-grade" : "";
    return `<tr class="${rowClass}">
    <td data-label="Fecha">${formatDateTime(e.ts, "—")}</td>
    <td data-label="Usuario">${esc(e.username || "—")}</td>
    <td data-label="Evento" class="evt"><span class="evt-type">${esc(EVENT_LABELS[e.event_type] || e.event_type)}</span></td>
    <td data-label="Detalle" class="muted">${esc(e.detail || "")}</td>
    <td data-label="IP" class="mono">${esc(e.ip || "")}</td>
  </tr>`;
  }).join("");
}

async function createUser() {
  const username = document.getElementById("newUser").value.trim();
  const is_admin = document.getElementById("newAdmin").checked;
  if (!username) return;
  try {
    const r = await api("/admin/api/users", { method: "POST", body: JSON.stringify({ username, is_admin }) });
    document.getElementById("newUser").value = "";
    document.getElementById("newAdmin").checked = false;
    toast(`Usuario <strong>${esc(r.username)}</strong> creado.<br>Clave temporal: <span class="mono">${esc(r.temp_password)}</span><br>Compártela; la cambiará al ingresar.`);
    load();
  } catch (e) { toast("Error: " + esc(e.message)); }
}

async function resetPwd(u) {
  if (!confirm(`¿Reiniciar la clave de ${u}?`)) return;
  try {
    const r = await api(`/admin/api/users/${encodeURIComponent(u)}/reset-password`, { method: "POST" });
    toast(`Nueva clave temporal de <strong>${esc(u)}</strong>: <span class="mono">${esc(r.temp_password)}</span>`);
    load();
  } catch (e) { toast("Error: " + esc(e.message)); }
}

async function toggleBlock(u, blocked) {
  try { await api(`/admin/api/users/${encodeURIComponent(u)}/block`, { method: "POST", body: JSON.stringify({ blocked }) }); load(); }
  catch (e) { toast("Error: " + esc(e.message)); }
}

async function toggleAdmin(u, is_admin) {
  try { await api(`/admin/api/users/${encodeURIComponent(u)}/admin`, { method: "POST", body: JSON.stringify({ is_admin }) }); load(); }
  catch (e) { toast("Error: " + esc(e.message)); }
}

async function delUser(u) {
  if (!confirm(`¿Eliminar el usuario ${u}? Esta acción no se puede deshacer.`)) return;
  try { await api(`/admin/api/users/${encodeURIComponent(u)}`, { method: "DELETE" }); load(); }
  catch (e) { toast("Error: " + esc(e.message)); }
}

const initialSection = location.hash.slice(1) || "overview";
showAdminSection(initialSection, false);
load();
loadGlobalConfig();
setInterval(load, 15000);
