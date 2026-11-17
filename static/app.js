/* Asesor Pedagógico Inteligente — SPA sin dependencias (CSP: solo scripts propios). */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const app = $("#app");
const state = { user: null, cohortes: [], estudiantes: [] };

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = (n, d = 1) => (n === null || n === undefined ? "—" : Number(n).toFixed(d).replace(".", ","));
const fecha = (iso) => (iso ? new Date(iso).toLocaleString("es-CO", { dateStyle: "medium", timeStyle: "short" }) : "—");
const notaClase = (n) => (n === null || n === undefined ? "" : n >= 4 ? "ok" : n >= 3 ? "warn" : "bad");
const nivelTexto = (n) => (n == null ? "Sin nota" : n >= 4.5 ? "Excelente" : n >= 4 ? "Sobresaliente" : n >= 3.5 ? "Bueno" : n >= 3 ? "Aceptable" : "Insuficiente");

function toast(msg, error = false) {
  const t = $("#toast");
  t.textContent = msg;
  t.className = "toast" + (error ? " error" : "");
  t.hidden = false;
  clearTimeout(toast._t);
  toast._t = setTimeout(() => (t.hidden = true), error ? 7000 : 3500);
}

async function api(path, opts = {}) {
  const o = { credentials: "same-origin", ...opts, headers: { ...(opts.headers || {}) } };
  if (o.body && !(o.body instanceof FormData) && typeof o.body !== "string") {
    o.body = JSON.stringify(o.body);
    o.headers["Content-Type"] = "application/json";
  }
  const r = await fetch("/api" + path, o);
  if (r.status === 401 && !path.startsWith("/auth/login")) {
    state.user = null;
    location.hash = "#/login";
    throw new Error("Sesión vencida");
  }
  const ct = r.headers.get("content-type") || "";
  const data = ct.includes("json") ? await r.json() : await r.blob();
  if (!r.ok) {
    const det = data && data.detail;
    const err = new Error(typeof det === "string" ? det : det?.mensaje || (Array.isArray(det) ? det.map((d) => d.msg).join("; ") : "Error " + r.status));
    err.detalle = det;
    err.status = r.status;
    throw err;
  }
  return data;
}

function busy(btn, on, texto) {
  if (!btn) return;
  if (on) {
    btn.dataset.txt = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner"></span> ${esc(texto || "Procesando…")}`;
  } else {
    btn.disabled = false;
    btn.innerHTML = btn.dataset.txt || btn.innerHTML;
  }
}

/* ---------------------------------------------------------------- router */
const routes = [];
const route = (pattern, fn, rol) => routes.push({ re: new RegExp("^" + pattern.replace(/:(\w+)/g, "(?<$1>[^/]+)") + "$"), fn, rol });

async function render() {
  const hash = location.hash.slice(1) || "/";
  const [path, qs] = hash.split("?");
  const params = Object.fromEntries(new URLSearchParams(qs || ""));
  if (!state.user && path !== "/login") {
    try {
      state.user = (await api("/auth/me")).usuario;
    } catch {
      location.hash = "#/login";
      return;
    }
  }
  renderNav(path);
  for (const r of routes) {
    const m = path.match(r.re);
    if (m) {
      if (r.rol && state.user?.rol !== r.rol) {
        app.innerHTML = `<div class="card empty">No tiene permiso para ver esta página.</div>`;
        return;
      }
      app.innerHTML = `<div class="empty"><span class="spinner"></span></div>`;
      try {
        await r.fn({ ...(m.groups || {}), ...params });
      } catch (e) {
        if (e.message !== "Sesión vencida") app.innerHTML = `<div class="card"><h2>No se pudo cargar</h2><p class="muted">${esc(e.message)}</p></div>`;
      }
      window.scrollTo(0, 0);
      return;
    }
  }
  app.innerHTML = `<div class="card empty">Página no encontrada. <a href="#/">Volver al inicio</a></div>`;
}

function renderNav(path) {
  const top = $("#topbar");
  if (!state.user) {
    top.hidden = true;
    return;
  }
  top.hidden = false;
  top.classList.remove("open");
  const doc = state.user.rol === "docente";
  const links = doc
    ? [["/", "Panel"], ["/revisiones", "Revisiones"], ["/informes", "Informes"], ["/usuarios", "Estudiantes"], ["/config", "Modelo y sandbox"], ["/auditoria", "Auditoría"]]
    : [["/", "Mis trabajos"], ["/subir", "Subir trabajo"], ["/informe/estudiante/" + state.user.id, "Mi informe"]];
  $("#nav").innerHTML = links
    .map(([h, t]) => `<a href="#${h}" class="${path === h || (h !== "/" && path.startsWith(h)) ? "active" : ""}">${t}</a>`)
    .join("");
  $("#userBox").innerHTML = `<span>${esc(state.user.nombre)} · <span class="badge accent">${esc(state.user.rol)}</span></span>
    <button class="btn sm" id="logoutBtn">Salir</button>`;
  $("#logoutBtn").onclick = async () => {
    await api("/auth/logout", { method: "POST" });
    state.user = null;
    location.hash = "#/login";
  };
}
$("#menuBtn").onclick = () => $("#topbar").classList.toggle("open");
window.addEventListener("hashchange", render);

/* ---------------------------------------------------------------- login */
route("/login", async () => {
  app.innerHTML = `
  <div class="login card">
    <span class="logo"><svg viewBox="0 0 32 32"><path d="M9 21l4-10 3 7 2-4 5 7"/></svg></span>
    <h1>Asesor Pedagógico Inteligente</h1>
    <p class="muted">Evaluación de laboratorios de IA con evidencias verificadas y revisión docente.</p>
    <form id="loginForm">
      <div class="field"><label for="email">Correo</label><input id="email" type="email" autocomplete="username" required></div>
      <div class="field"><label for="pass">Contraseña</label><input id="pass" type="password" autocomplete="current-password" required></div>
      <button class="btn primary" style="width:100%;justify-content:center">Ingresar</button>
    </form>
    <div class="demo-box card flat">
      <strong>Cuentas de demostración</strong>
      <div class="muted">Docente: docente@demo.edu.co<br>Estudiante: ana.gomez@demo.edu.co<br>Contraseña: la definida en DEMO_PASSWORD (ver manual).</div>
    </div>
  </div>`;
  $("#loginForm").onsubmit = async (ev) => {
    ev.preventDefault();
    const b = ev.target.querySelector("button");
    busy(b, true, "Ingresando…");
    try {
      state.user = (await api("/auth/login", { method: "POST", body: { email: $("#email").value, password: $("#pass").value } })).usuario;
      location.hash = "#/";
    } catch (e) {
      toast(e.message, true);
      busy(b, false);
    }
  };
});

/* ---------------------------------------------------------------- panel */
route("/", async () => {
  state.cohortes = await api("/cohortes");
  if (state.user.rol !== "docente") return panelEstudiante();
  const pend = await api("/revisiones/pendientes");
  const labs = state.cohortes.flatMap((c) => c.laboratorios);
  const entregas = labs.reduce((a, l) => a + l.entregas, 0);
  const publicadas = labs.reduce((a, l) => a + l.publicadas, 0);
  app.innerHTML = `
  <div class="page-head"><div><h1>Panel docente</h1><p>Portafolio de los cortes 1 y 2 con la rúbrica activa de cada laboratorio.</p></div>
    <a class="btn primary" href="#/subir">+ Cargar trabajo</a></div>
  <div class="grid g4" style="margin-bottom:16px">
    <div class="card stat"><span class="v">${labs.length}</span><span class="l">laboratorios</span></div>
    <div class="card stat"><span class="v">${entregas}</span><span class="l">entregas cargadas</span></div>
    <div class="card stat"><span class="v">${pend.length}</span><span class="l">pendientes de revisión</span></div>
    <div class="card stat"><span class="v">${publicadas}</span><span class="l">notas publicadas</span></div>
  </div>
  ${pend.length ? `<div class="card" style="margin-bottom:16px"><div class="row between"><h2>Pendientes de tu aprobación</h2><a href="#/revisiones">Ver todas</a></div>
    ${tablaPendientes(pend.slice(0, 5))}</div>` : ""}
  <div class="grid g2">
    ${state.cohortes.map((c) => `
      <div class="card"><h2>${esc(c.nombre)}</h2><p class="muted small">${esc(c.descripcion)}</p>
        <div class="stack">${c.laboratorios.map((l, i) => `
          <a class="lab" href="#/lab/${l.id}">
            <span class="ic">${i + 1}</span>
            <span class="meta"><strong>${esc(l.nombre)}</strong>
              <span class="small muted">${l.rubrica ? `Rúbrica v${l.rubrica.version} · ${l.rubrica.criterios} criterios` : "Sin rúbrica activa"} · ${l.entregas} entrega(s)</span></span>
            ${l.pendientes_revision ? `<span class="badge warn">${l.pendientes_revision} por revisar</span>` : l.rubrica ? "" : `<span class="badge bad">sin rúbrica</span>`}
          </a>`).join("")}</div>
      </div>`).join("")}
  </div>`;
});

function tablaPendientes(pend) {
  return `<div class="table-wrap"><table><thead><tr><th>Estudiante</th><th>Laboratorio</th><th class="num">Nota preliminar</th><th class="num">Evidencias verificadas</th><th>Alertas</th></tr></thead><tbody>
  ${pend.map((p) => `<tr class="click" data-href="#/entrega/${p.entrega_id}"><td>${esc(p.estudiante)}</td><td>${esc(p.laboratorio)}<div class="small muted">${esc(p.cohorte)}</div></td>
    <td class="num"><span class="badge ${notaClase(p.nota_preliminar)}">${fmt(p.nota_preliminar)}</span></td><td class="num">${fmt(p.confianza, 0)} %</td>
    <td>${p.alertas ? `<span class="badge warn">${p.alertas}</span>` : `<span class="badge ok">0</span>`}</td></tr>`).join("")}
  </tbody></table></div>`;
}
document.addEventListener("click", (ev) => {
  const tr = ev.target.closest("tr[data-href]");
  if (tr) location.hash = tr.dataset.href;
});

async function panelEstudiante() {
  const entregas = await api("/entregas");
  app.innerHTML = `
  <div class="page-head"><div><h1>Mis trabajos</h1><p>Solo ves notas aprobadas por el docente.</p></div>
    <div class="row"><a class="btn" href="#/informe/estudiante/${state.user.id}">Mi informe integrado</a><a class="btn primary" href="#/subir">+ Subir trabajo</a></div></div>
  <div class="grid g2">${state.cohortes.map((c) => `
    <div class="card"><h2>${esc(c.nombre)}</h2><div class="stack">
    ${c.laboratorios.map((l) => {
      const e = entregas.find((x) => x.laboratorio_id === l.id);
      return `<a class="lab" href="${e ? "#/entrega/" + e.id : "#/subir?lab=" + l.id}"><span class="meta"><strong>${esc(l.nombre)}</strong>
        <span class="small muted">${e ? "Entregado " + fecha(e.created_at) : "Pendiente de entrega"}</span></span>
        ${e?.nota_publicada != null ? `<span class="badge ${notaClase(e.nota_publicada)}">${fmt(e.nota_publicada)}</span>` : e ? `<span class="badge">en revisión</span>` : `<span class="badge accent">subir</span>`}</a>`;
    }).join("")}</div></div>`).join("")}</div>`;
}

/* ---------------------------------------------------------------- laboratorio */
route("/lab/:id", async ({ id }) => {
  state.cohortes = await api("/cohortes");
  const lab = state.cohortes.flatMap((c) => c.laboratorios.map((l) => ({ ...l, cohorte: c.nombre }))).find((l) => l.id == id);
  if (!lab) throw new Error("Laboratorio no encontrado");
  const [versiones, entregas] = await Promise.all([api(`/laboratorios/${id}/rubricas`), api(`/entregas?laboratorio_id=${id}`)]);
  const activa = lab.rubrica ? await api(`/rubricas/${lab.rubrica.id}`) : null;
  app.innerHTML = `
  <div class="crumbs"><a href="#/">Panel</a> / ${esc(lab.cohorte)}</div>
  <div class="page-head"><div><h1>${esc(lab.nombre)}</h1><p>${esc(lab.descripcion)} ${lab.requiere_codigo ? "· Exige código fuente" : "· Código opcional"}</p></div>
    <div class="row"><a class="btn" href="#/informe/laboratorio/${id}">Informe del laboratorio</a><a class="btn primary" href="#/subir?lab=${id}">+ Cargar trabajo</a></div></div>
  <div class="grid split-21">
    <div class="card">
      <div class="row between"><h2>Rúbrica activa ${activa ? `<span class="badge accent">v${activa.version}</span>` : ""}</h2>
        <a class="btn sm" href="#/rubrica/${id}${activa ? "?desde=" + activa.id : ""}">${activa ? "Editar (nueva versión)" : "Crear rúbrica"}</a></div>
      ${activa ? vistaRubrica(activa.contenido) + `<p class="small muted">SHA-256: <code>${activa.sha256.slice(0, 16)}…</code> · creada ${fecha(activa.created_at)}</p>`
        : `<div class="empty">Este laboratorio no tiene rúbrica válida. No se pueden cargar entregas hasta crearla.</div>`}
    </div>
    <div class="stack">
      <div class="card"><h2>Entregas</h2>
        ${entregas.length ? `<div class="table-wrap"><table><thead><tr><th>Estudiante</th><th>Estado</th><th class="num">Nota</th></tr></thead><tbody>
          ${entregas.map((e) => `<tr class="click" data-href="#/entrega/${e.id}"><td>${esc(e.estudiante)}<div class="small muted">rúbrica v${e.rubrica_version}</div></td>
          <td>${badgeEstado(e.estado)}</td><td class="num">${e.nota_publicada != null ? `<strong>${fmt(e.nota_publicada)}</strong>` : e.nota_preliminar != null ? `<span class="muted">${fmt(e.nota_preliminar)} prel.</span>` : "—"}</td></tr>`).join("")}
          </tbody></table></div>` : `<div class="empty">Aún no hay entregas.</div>`}
      </div>
      <div class="card"><h2>Historial de versiones</h2>
        ${versiones.length ? `<table><tbody>${versiones.map((v) => `<tr><td>v${v.version}</td><td>${v.valida ? (v.activa ? `<span class="badge ok">activa</span>` : `<span class="badge">válida</span>`) : `<span class="badge bad">rechazada (${v.errores.length} errores)</span>`}</td>
          <td class="small muted">${esc(v.origen)} · ${fecha(v.created_at)}</td>
          <td>${v.valida && !v.activa ? `<button class="btn sm" data-activar="${v.id}">Activar</button>` : !v.valida ? `<a class="btn sm" href="#/rubrica/${id}?desde=${v.id}">Corregir</a>` : ""}</td></tr>`).join("")}</tbody></table>` : `<p class="muted">Sin versiones.</p>`}
      </div>
    </div>
  </div>`;
  $$("[data-activar]").forEach((b) => (b.onclick = async () => {
    try { await api(`/rubricas/${b.dataset.activar}/activar`, { method: "POST" }); toast("Versión activada"); render(); } catch (e) { toast(e.message, true); }
  }));
});

const badgeEstado = (s) => ({ cargada: `<span class="badge">cargada</span>`, verificada: `<span class="badge info">verificada</span>`, evaluada: `<span class="badge warn">por revisar</span>`, publicada: `<span class="badge ok">publicada</span>` }[s] || `<span class="badge">${esc(s)}</span>`);

function vistaRubrica(r) {
  const comp = Object.fromEntries(r.competencias.map((c) => [c.id, c.nombre]));
  return `<p><strong>${esc(r.nombre)}</strong><br><span class="muted small">${esc(r.descripcion || "")}</span></p>
  <div class="table-wrap"><table><thead><tr><th>Criterio</th><th>Competencia</th><th class="num">Peso</th><th>Fuente</th><th>Niveles (puntaje)</th></tr></thead><tbody>
  ${r.criterios.map((c) => `<tr><td><strong>${esc(c.id)}</strong> ${esc(c.nombre)}<div class="small muted">${esc(c.descripcion || "")}</div></td>
    <td class="small">${esc(c.competencia_id)} · ${esc(comp[c.competencia_id] || "")}</td><td class="num">${c.peso} %</td>
    <td>${c.fuente === "llm" ? `<span class="badge accent">LLM + evidencia</span>` : c.fuente === "pruebas" ? `<span class="badge info">pruebas (auto)</span>` : `<span class="badge info">análisis estático (auto)</span>`}</td>
    <td class="small">${c.niveles.map((n) => `<div title="${esc(n.descriptor)}">${esc(n.nombre)} <span class="muted">(${fmt(n.puntaje)}${n.umbral_min != null ? `, ≥${n.umbral_min}` : ""})</span></div>`).join("")}</td></tr>`).join("")}
  </tbody></table></div>`;
}

/* ---------------------------------------------------------------- editor de rúbrica */
const plantillaRubrica = () => ({
  nombre: "Nueva rúbrica",
  descripcion: "",
  competencias: [{ id: "RA1", nombre: "Analizar fundamentos y modelos de IA", descripcion: "" }],
  criterios: [{
    id: "CR1", competencia_id: "RA1", nombre: "Criterio 1", descripcion: "", peso: 100, fuente: "llm",
    niveles: [
      { id: "N1", nombre: "Insuficiente", puntaje: 1.5, descriptor: "" },
      { id: "N2", nombre: "Básico", puntaje: 3, descriptor: "" },
      { id: "N3", nombre: "Competente", puntaje: 4, descriptor: "" },
      { id: "N4", nombre: "Destacado", puntaje: 5, descriptor: "" },
    ],
  }],
});

route("/rubrica/:lab", async ({ lab, desde }) => {
  const origen = desde ? await api(`/rubricas/${desde}`) : null;
  let rub = origen ? origen.contenido : plantillaRubrica();
  rub = JSON.parse(JSON.stringify(rub));
  const competenciasCurso = await api("/competencias");
  let modo = "visual";

  function pintar(errores = null, adv = null) {
    const total = rub.criterios.reduce((a, c) => a + (Number(c.peso) || 0), 0);
    app.innerHTML = `
    <div class="crumbs"><a href="#/">Panel</a> / <a href="#/lab/${lab}">Laboratorio</a></div>
    <div class="page-head"><div><h1>Editor de rúbrica</h1><p>Guardar crea una versión nueva e inmutable. Las entregas conservan la versión con la que se subieron.</p></div>
      <div class="row"><button class="btn" id="btnValidar">Validar</button><button class="btn primary" id="btnGuardar">Guardar versión</button></div></div>
    ${errores?.length ? `<ul class="err-list">${errores.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>` : ""}
    ${adv?.length ? `<ul class="warn-list">${adv.map((e) => `<li>${esc(e)}</li>`).join("")}</ul>` : ""}
    ${errores && !errores.length ? `<div class="alert baja" style="margin-bottom:12px">✓ La rúbrica es válida y coherente.</div>` : ""}
    <div class="card" style="margin-bottom:16px">
      <div class="row between"><div class="pill-tabs" style="margin:0"><button data-modo="visual" class="${modo === "visual" ? "active" : ""}">Editor visual</button><button data-modo="json" class="${modo === "json" ? "active" : ""}">JSON</button></div>
      <div class="row"><label class="btn sm" style="margin:0">Importar archivo (JSON, PDF, DOCX)<input type="file" id="fileRub" accept=".json,.pdf,.docx,.txt,.md" hidden></label></div></div>
      <p class="small muted" style="margin-top:8px">PDF/DOCX se convierten con el modelo configurado y luego se validan. Si hay errores, la versión queda como borrador para corregir aquí.</p>
    </div>
    ${modo === "json" ? `<div class="card"><textarea class="code" id="jsonRub">${esc(JSON.stringify(rub, null, 2))}</textarea></div>` : `
    <div class="card" style="margin-bottom:16px"><div class="grid g2">
      <div class="field"><label>Nombre</label><input data-k="nombre" value="${esc(rub.nombre)}"></div>
      <div class="field"><label>Descripción</label><input data-k="descripcion" value="${esc(rub.descripcion || "")}"></div></div>
      <h3>Competencias</h3>
      ${rub.competencias.map((c, i) => `<div class="comp-row"><input data-comp="${i}" data-f="id" value="${esc(c.id)}" list="catalogo">
        <input data-comp="${i}" data-f="nombre" value="${esc(c.nombre)}" placeholder="Nombre"><button class="btn sm ghost danger" data-delcomp="${i}">✕</button></div>`).join("")}
      <datalist id="catalogo">${competenciasCurso.map((c) => `<option value="${esc(c.codigo)}">${esc(c.nombre)}</option>`).join("")}</datalist>
      <button class="btn sm" id="addComp">+ Competencia</button>
    </div>
    <div class="card"><div class="row between"><h2>Criterios</h2><span class="badge ${Math.abs(total - 100) < 0.01 ? "ok" : "bad"}">Pesos: ${total} %</span></div>
      ${rub.criterios.map((c, i) => `<div class="ed-crit">
        <div class="ed-row"><div><label>Id</label><input data-cr="${i}" data-f="id" value="${esc(c.id)}"></div>
          <div><label>Nombre</label><input data-cr="${i}" data-f="nombre" value="${esc(c.nombre)}"></div>
          <div><label>Competencia</label><select data-cr="${i}" data-f="competencia_id">${rub.competencias.map((k) => `<option ${k.id === c.competencia_id ? "selected" : ""}>${esc(k.id)}</option>`).join("")}</select></div>
          <div><label>Peso %</label><input type="number" step="0.5" data-cr="${i}" data-f="peso" value="${c.peso}"></div>
          <button class="btn sm ghost danger" data-delcr="${i}">Quitar</button></div>
        <div class="grid g2" style="margin-top:8px"><div><label>Descripción</label><input data-cr="${i}" data-f="descripcion" value="${esc(c.descripcion || "")}"></div>
          <div><label>Fuente de evaluación</label><select data-cr="${i}" data-f="fuente">
            <option value="llm" ${c.fuente === "llm" ? "selected" : ""}>LLM con evidencias citadas</option>
            <option value="pruebas" ${c.fuente === "pruebas" ? "selected" : ""}>Automática: % de pruebas aprobadas</option>
            <option value="analisis_estatico" ${c.fuente === "analisis_estatico" ? "selected" : ""}>Automática: índice de análisis estático</option></select></div></div>
        <div class="small muted" style="margin-top:8px">Niveles de desempeño (puntaje 0–5${c.fuente !== "llm" ? "; umbral mínimo de la métrica 0–100" : ""})</div>
        ${c.niveles.map((n, j) => `<div class="ed-niv"><input data-cr="${i}" data-niv="${j}" data-f="id" value="${esc(n.id)}" title="Id">
          <input data-cr="${i}" data-niv="${j}" data-f="nombre" value="${esc(n.nombre)}" placeholder="Nombre">
          <input type="number" step="0.1" min="0" max="5" data-cr="${i}" data-niv="${j}" data-f="puntaje" value="${n.puntaje}" title="Puntaje">
          <input type="number" step="1" min="0" max="100" data-cr="${i}" data-niv="${j}" data-f="umbral_min" value="${n.umbral_min ?? ""}" placeholder="umbral" ${c.fuente === "llm" ? "disabled" : ""}>
          <input data-cr="${i}" data-niv="${j}" data-f="descriptor" value="${esc(n.descriptor)}" placeholder="Descriptor de desempeño">
          <button class="btn sm ghost danger" data-delniv="${i}:${j}">✕</button></div>`).join("")}
        <button class="btn sm" data-addniv="${i}" style="margin-top:6px">+ Nivel</button>
      </div>`).join("")}
      <button class="btn" id="addCr">+ Criterio</button></div>`}`;
    bind();
  }

  function leerJSON() {
    if (modo !== "json") return true;
    try { rub = JSON.parse($("#jsonRub").value); return true; } catch (e) { toast("JSON inválido: " + e.message, true); return false; }
  }

  function bind() {
    $$("[data-modo]").forEach((b) => (b.onclick = () => { if (!leerJSON()) return; modo = b.dataset.modo; pintar(); }));
    $$("[data-k]").forEach((i) => (i.oninput = () => (rub[i.dataset.k] = i.value)));
    $$("[data-comp]").forEach((i) => (i.oninput = () => (rub.competencias[i.dataset.comp][i.dataset.f] = i.value)));
    $$("[data-cr]").forEach((i) => {
      const ev = i.tagName === "SELECT" ? "onchange" : "oninput";
      i[ev] = () => {
        const c = rub.criterios[i.dataset.cr];
        const tgt = i.dataset.niv !== undefined ? c.niveles[i.dataset.niv] : c;
        let v = i.value;
        if (["peso", "puntaje"].includes(i.dataset.f)) v = v === "" ? 0 : Number(v);
        if (i.dataset.f === "umbral_min") v = v === "" ? null : Number(v);
        tgt[i.dataset.f] = v;
        if (i.dataset.f === "fuente" || i.dataset.f === "peso") pintar();
      };
    });
    $("#addComp") && ($("#addComp").onclick = () => { rub.competencias.push({ id: "RA" + (rub.competencias.length + 1), nombre: "", descripcion: "" }); pintar(); });
    $$("[data-delcomp]").forEach((b) => (b.onclick = () => { rub.competencias.splice(b.dataset.delcomp, 1); pintar(); }));
    $("#addCr") && ($("#addCr").onclick = () => { const p = plantillaRubrica().criterios[0]; p.id = "CR" + (rub.criterios.length + 1); p.peso = 0; p.competencia_id = rub.competencias[0]?.id || ""; rub.criterios.push(p); pintar(); });
    $$("[data-delcr]").forEach((b) => (b.onclick = () => { rub.criterios.splice(b.dataset.delcr, 1); pintar(); }));
    $$("[data-addniv]").forEach((b) => (b.onclick = () => { const c = rub.criterios[b.dataset.addniv]; c.niveles.push({ id: "N" + (c.niveles.length + 1), nombre: "", puntaje: 5, descriptor: "" }); pintar(); }));
    $$("[data-delniv]").forEach((b) => (b.onclick = () => { const [i, j] = b.dataset.delniv.split(":"); rub.criterios[i].niveles.splice(j, 1); pintar(); }));
    $("#btnValidar").onclick = async () => {
      if (!leerJSON()) return;
      const r = await api("/rubricas/validar", { method: "POST", body: { contenido: rub } });
      pintar(r.errores, r.advertencias);
    };
    $("#btnGuardar").onclick = async (ev) => {
      if (!leerJSON()) return;
      busy(ev.target, true, "Guardando…");
      try {
        const r = await api(`/laboratorios/${lab}/rubricas`, { method: "POST", body: { contenido: rub, origen: modo === "json" ? "json" : "formulario", activar: true } });
        toast(`Rúbrica v${r.version} guardada y activada`);
        location.hash = `#/lab/${lab}`;
      } catch (e) {
        if (e.detalle?.errores) { pintar(e.detalle.errores, e.detalle.advertencias); toast("Rúbrica rechazada: se guardó como borrador para corregir", true); }
        else toast(e.message, true);
      }
    };
    $("#fileRub").onchange = async (ev) => {
      const f = ev.target.files[0];
      if (!f) return;
      const fd = new FormData();
      fd.append("archivo", f);
      toast("Procesando " + f.name + "…");
      try {
        const r = await api(`/laboratorios/${lab}/rubricas/documento`, { method: "POST", body: fd });
        toast(`Rúbrica importada como v${r.version} y activada`);
        location.hash = `#/lab/${lab}`;
      } catch (e) {
        if (e.detalle?.borrador_id) {
          rub = (await api(`/rubricas/${e.detalle.borrador_id}`)).contenido;
          pintar(e.detalle.errores, e.detalle.advertencias);
          toast("Rúbrica importada con problemas: corrígela y guarda", true);
        } else toast(e.message, true);
      }
    };
  }
  if (origen && !origen.valida) pintar(origen.errores, origen.advertencias);
  else pintar();
});

/* ---------------------------------------------------------------- subir entrega */
route("/subir", async ({ lab }) => {
  state.cohortes = await api("/cohortes");
  const doc = state.user.rol === "docente";
  if (doc) state.estudiantes = await api("/usuarios?rol=estudiante");
  app.innerHTML = `
  <div class="page-head"><div><h1>Cargar trabajo</h1><p>Informe PDF con texto legible + código fuente (ZIP o GitHub). Se asocia la versión vigente de la rúbrica.</p></div></div>
  <form class="card" id="formEntrega" style="max-width:760px">
    <div class="grid g2">
      <div class="field"><label>Laboratorio</label><select name="laboratorio_id" id="selLab" required>
        ${state.cohortes.map((c) => `<optgroup label="${esc(c.nombre)}">${c.laboratorios.map((l) => `<option value="${l.id}" ${l.id == lab ? "selected" : ""} ${l.rubrica ? "" : "disabled"}>${esc(l.nombre)}${l.rubrica ? "" : " (sin rúbrica)"}</option>`).join("")}</optgroup>`).join("")}
      </select><div class="hint" id="rubInfo"></div></div>
      ${doc ? `<div class="field"><label>Estudiante</label><select name="estudiante_id" required>${state.estudiantes.map((s) => `<option value="${s.id}">${esc(s.nombre)}</option>`).join("")}</select></div>` : ""}
    </div>
    <div class="field"><label>Informe (PDF de texto legible) *</label><input type="file" name="informe" accept="application/pdf" required>
      <div class="hint">Exportado desde Word/Docs. Un PDF escaneado se rechaza porque no permite verificar evidencias.</div></div>
    <div class="grid g2">
      <div class="field"><label>Código fuente (ZIP)</label><input type="file" name="codigo_zip" accept=".zip"></div>
      <div class="field"><label>…o repositorio de GitHub</label><input name="github_url" placeholder="https://github.com/usuario/repo"><div class="hint">Se fija el commit exacto para reproducibilidad.</div></div>
    </div>
    <details><summary>Anexos opcionales (video o presentación)</summary>
      <div class="grid g2" style="margin-top:10px"><div class="field"><label>Enlace</label><input name="extra_url" placeholder="https://youtube.com/…"></div>
      <div class="field"><label>Archivo</label><input type="file" name="extra" accept=".mp4,.webm,.mov,.pptx,.pdf,.odp"></div></div></details>
    <hr><div class="row"><button class="btn primary">Cargar entrega</button><span class="small muted">Tamaño máximo del informe: 25 MB.</span></div>
  </form>`;
  const info = () => {
    const l = state.cohortes.flatMap((c) => c.laboratorios).find((x) => x.id == $("#selLab").value);
    $("#rubInfo").textContent = l?.rubrica ? `Se usará la rúbrica v${l.rubrica.version} (${l.rubrica.criterios} criterios). ${l.requiere_codigo ? "Exige código." : "Código opcional."}` : "";
  };
  $("#selLab").onchange = info;
  info();
  $("#formEntrega").onsubmit = async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    for (const k of ["codigo_zip", "extra"]) if (!fd.get(k)?.size) fd.delete(k);
    const b = ev.target.querySelector("button.primary");
    busy(b, true, "Subiendo y extrayendo texto…");
    try {
      const e = await api("/entregas", { method: "POST", body: fd });
      toast("Entrega cargada");
      location.hash = "#/entrega/" + e.id;
    } catch (e) { toast(e.message, true); busy(b, false); }
  };
});

/* ---------------------------------------------------------------- detalle de entrega */
route("/entrega/:id", async ({ id }) => {
  const e = await api("/entregas/" + id);
  const doc = state.user.rol === "docente";
  const evs = e.evaluaciones || [];
  const actual = evs.find((x) => x.estado === "preliminar") || evs.find((x) => x.estado === "publicada");
  const publicada = evs.find((x) => x.estado === "publicada");
  const v = e.verificacion;
  const paso = publicada && !evs.some((x) => x.estado === "preliminar") ? 6 : actual ? 4 : v ? 2 : 1;
  const pasos = ["Cargar", "Verificar evidencias", "Puntuar criterios", "Calcular nota", "Retroalimentar", "Aprobar", "Informe"];

  app.innerHTML = `
  <div class="crumbs"><a href="#/">Inicio</a> / ${doc ? `<a href="#/lab/${e.laboratorio_id}">${esc(e.laboratorio)}</a>` : esc(e.laboratorio)}</div>
  <div class="page-head"><div><h1>${esc(e.laboratorio)}</h1><p>${esc(e.estudiante)} · ${esc(e.cohorte)} · ${badgeEstado(e.estado)}</p></div>
    ${doc ? `<div class="row"><button class="btn" id="btnVerificar">${v ? "Repetir verificación" : "Verificar código"}</button>
      <button class="btn primary" id="btnEvaluar">${actual ? "Re-evaluar con IA" : "Evaluar con IA"}</button></div>` : ""}</div>
  ${doc ? `<div class="steps" style="margin-bottom:16px">${pasos.map((p, i) => `<span class="${i < paso ? "done" : i === paso ? "now" : ""}">${i + 1}. ${p}</span>`).join("")}</div>` : ""}
  <div class="grid split-12">
    <div class="stack">
      <div class="card"><h2>Material entregado</h2>
        <dl class="kv"><dt>Informe</dt><dd><a href="/api/entregas/${e.id}/informe.pdf" target="_blank">${esc(e.pdf_nombre)}</a> (${e.pdf_paginas} págs.)</dd>
        <dt>SHA-256 informe</dt><dd><code>${e.pdf_sha256.slice(0, 20)}…</code></dd>
        <dt>Código</dt><dd>${e.codigo_origen ? `${e.codigo_origen === "github" ? `<a href="${esc(e.codigo_ref)}" target="_blank" rel="noopener">GitHub</a> @ <code>${esc((e.codigo_commit || "").slice(0, 10))}</code>` : "ZIP"} · ${e.codigo_archivos} archivos` : "no incluido"}</dd>
        ${e.codigo_sha256 ? `<dt>SHA-256 código</dt><dd><code>${e.codigo_sha256.slice(0, 20)}…</code></dd>` : ""}
        ${e.extra_url ? `<dt>Enlace</dt><dd><a href="${esc(e.extra_url)}" target="_blank" rel="noopener">${esc(e.extra_url)}</a></dd>` : ""}
        ${e.extra_nombre ? `<dt>Anexo</dt><dd><a href="/api/entregas/${e.id}/anexo">${esc(e.extra_nombre)}</a></dd>` : ""}
        <dt>Rúbrica usada</dt><dd>v${e.rubrica_version} · ${esc(e.rubrica_nombre)}</dd><dt>Cargada</dt><dd>${fecha(e.created_at)}</dd></dl>
      </div>
      ${doc ? vistaVerificacion(v) : ""}
    </div>
    <div class="stack" id="evalCol">
      ${actual ? vistaEvaluacion(actual, e, doc) : `<div class="card empty">${doc ? "Aún no se ha evaluado. Pulsa «Evaluar con IA»: primero se verifica el código en el sandbox y luego el modelo puntúa cada criterio con evidencias." : "Tu trabajo está en revisión. Verás la nota cuando el docente la apruebe."}</div>`}
      ${doc && evs.length > 1 ? `<div class="card"><h3>Historial de evaluaciones</h3><table><tbody>${evs.map((x) => `<tr><td>#${x.id}</td><td>${esc(x.estado)}</td><td class="num">${fmt(x.nota_final ?? x.nota_preliminar)}</td><td class="small muted">${esc(x.trazabilidad.proveedor)}/${esc(x.trazabilidad.modelo)} · ${fecha(x.created_at)}</td></tr>`).join("")}</tbody></table></div>` : ""}
    </div>
  </div>`;

  if (doc) {
    $("#btnVerificar").onclick = async (ev) => {
      busy(ev.target, true, "Ejecutando en sandbox…");
      try { await api(`/entregas/${id}/verificar`, { method: "POST" }); toast("Verificación completada"); render(); } catch (er) { toast(er.message, true); busy(ev.target, false); }
    };
    $("#btnEvaluar").onclick = async (ev) => {
      busy(ev.target, true, "Evaluando (puede tardar)…");
      try { const r = await api(`/entregas/${id}/evaluar`, { method: "POST" }); toast(`Nota preliminar ${fmt(r.nota_preliminar)} calculada por el backend`); render(); } catch (er) { toast(er.message, true); busy(ev.target, false); }
    };
    bindRevision(actual, e);
  }
});

function vistaVerificacion(v) {
  if (!v) return `<div class="card"><h2>Verificación objetiva</h2><p class="muted">Pendiente. Corre análisis estático (ruff) y pruebas unitarias (pytest) en un sandbox sin red.</p></div>`;
  const a = v.analisis || {}, p = v.pruebas || {}, s = v.sandbox || {}, m = a.metricas || {};
  return `<div class="card"><h2>Verificación objetiva</h2>
    <h3>Pruebas unitarias</h3>
    ${p.ejecutadas && p.total ? `<div class="row"><span class="nota" style="font-size:1.8rem">${p.aprobadas}/${p.total}</span><span class="badge ${p.tasa_exito >= 80 ? "ok" : p.tasa_exito >= 50 ? "warn" : "bad"}">${fmt(p.tasa_exito, 0)} % aprobadas</span></div>
      ${p.fallidas || p.errores ? `<p class="small" style="color:var(--bad)">${p.fallidas} fallidas · ${p.errores} con error</p>` : ""}` : `<p class="muted small">${esc(p.motivo || "No ejecutadas")}</p>`}
    ${s.modo ? `<p class="small muted">Sandbox: <strong>${esc(s.modo)}</strong> (aislamiento ${esc(s.aislamiento)}) · red ${esc(s.red)} · ${s.duracion_s}s de ${s.limites?.timeout_s}s · ${s.limites?.memoria_mb} MB${s.tiempo_agotado ? ' · <span style="color:var(--bad)">tiempo agotado</span>' : ""}</p>` : ""}
    ${p.casos?.length ? `<details><summary class="small">Casos (${p.casos.length})</summary><ul class="clean small">${p.casos.map((c) => `<li>${c.estado === "aprobada" ? "✓" : "✗"} <code>${esc(c.nombre)}</code></li>`).join("")}</ul></details>` : ""}
    ${p.salida ? `<details><summary class="small">Salida de pytest</summary><pre class="out">${esc(p.salida)}</pre></details>` : ""}
    <h3 style="margin-top:14px">Análisis estático</h3>
    ${a.disponible ? `<div class="row"><span class="nota" style="font-size:1.8rem">${fmt(a.calidad, 0)}<small>/100</small></span><span class="small muted">${a.hallazgos} hallazgos (${a.severos} severos) · ${a.densidad_por_100_lineas} por 100 líneas</span></div>
      ${a.muestras?.length ? `<details><summary class="small">Hallazgos</summary><ul class="clean small">${a.muestras.map((x) => `<li><code>${esc(x.codigo)}</code> ${esc(x.archivo)}:${x.linea} — ${esc(x.mensaje)}</li>`).join("")}</ul></details>` : ""}` : `<p class="muted small">${esc(a.motivo || "")}</p>`}
    <p class="small muted">${m.archivos_python ?? 0} archivos .py · ${m.lineas_codigo ?? 0} líneas · ${m.funciones ?? 0} funciones (${m.funciones_documentadas_pct ?? 0} % documentadas) · ${m.archivos_prueba ?? 0} archivos de prueba${m.errores_sintaxis?.length ? ` · <span style="color:var(--bad)">${m.errores_sintaxis.length} errores de sintaxis</span>` : ""}</p>
  </div>`;
}

function vistaEvaluacion(ev, e, doc) {
  const r = ev.respuesta || {};
  const pub = ev.estado === "publicada";
  const nota = pub ? ev.nota_final : ev.nota_preliminar;
  const crit = ev.resultado.criterios;
  const calc = ev.resultado.calculo;
  const repro = ev.resultado.reproducibilidad;
  return `
  <div class="card">
    <div class="row between" style="align-items:flex-start">
      <div><div class="small muted">${pub ? "Nota publicada" : "Nota preliminar (requiere aprobación docente)"}</div>
        <div class="nota">${fmt(nota)}<small> / 5,0</small></div><div class="muted">${nivelTexto(nota)}${pub && ev.decision === "ajustada" ? ` · ajustada por el docente${doc ? ` (preliminar ${fmt(ev.nota_preliminar)})` : ""}` : ""}</div></div>
      ${doc ? `<div style="min-width:180px"><div class="small muted">Evidencias verificadas en el material</div><div class="stat"><span class="v">${fmt(ev.confianza, 0)} %</span></div>
        <div class="bar ${ev.confianza >= 80 ? "" : ev.confianza >= 50 ? "warn" : "bad"}"><span style="width:${ev.confianza}%"></span></div></div>` : ""}
    </div>
    ${doc && calc ? `<p class="small muted" style="margin-top:10px">${pub && ev.decision === "ajustada" ? "Cálculo preliminar (antes del ajuste docente; la nota final se recalculó en el servidor con los niveles ajustados): " : "Cálculo en el backend: "} ${calc.detalle.map((d) => `${d.peso}%×${fmt(d.puntaje)}`).join(" + ")} = ${fmt(calc.nota_sin_redondeo, 3)} → <strong>${fmt(calc.nota)}</strong></p>` : ""}
    ${ev.comentario_docente ? `<div class="alert baja" style="margin-top:10px">💬 Docente: ${esc(ev.comentario_docente)}</div>` : ""}
    ${doc && ev.justificacion_docente ? `<p class="small muted">Justificación del ajuste: ${esc(ev.justificacion_docente)}</p>` : ""}
  </div>
  ${doc && ev.alertas?.length ? `<div class="card"><h3>Alertas para la revisión</h3>${ev.alertas.map((a) => `<div class="alert ${esc(a.severidad)}">⚠ ${esc(a.mensaje)}</div>`).join("")}
    ${repro ? `<p class="small muted" style="margin-top:8px">Reproducibilidad: misma entrada que la evaluación #${repro.comparada_con} → ${repro.identica ? "niveles idénticos ✓" : repro.criterios_distintos.length + " criterio(s) distintos"}</p>` : ""}</div>` : ""}
  <div class="card"><h2>Puntuación por criterio</h2>
    ${crit.map((c) => `<div class="criterio"><header><div><strong>${esc(c.nombre)}</strong> <span class="small muted">${esc(c.criterio_id)} · ${esc(c.competencia_id)} · peso ${c.peso} %</span>
      <div class="small muted">${c.metodo === "llm" ? "Evaluado por el modelo con evidencias" : "Nivel calculado automáticamente por el backend"}</div></div>
      <div class="row">${(() => { const aj = pub && ev.ajustes?.[c.criterio_id]; const n = aj ? (e.rubrica.criterios.find((x) => x.id === c.criterio_id)?.niveles || []).find((x) => x.id === aj) : null;
        return n ? `<span class="badge ${notaClase(n.puntaje)}">${esc(n.nombre)} · ${fmt(n.puntaje)}</span>${doc ? `<span class="small muted" style="text-decoration:line-through">${esc(c.nivel_nombre)}</span>` : ""}` : `<span class="badge ${notaClase(c.puntaje)}">${esc(c.nivel_nombre)} · ${fmt(c.puntaje)}</span>`; })()}
      ${doc && ev.estado === "preliminar" ? `<select class="ajuste" data-crit="${esc(c.criterio_id)}" style="width:auto">${(e.rubrica.criterios.find((x) => x.id === c.criterio_id)?.niveles || []).map((n) => `<option value="${esc(n.id)}" ${n.id === c.nivel_id ? "selected" : ""}>${esc(n.nombre)} (${fmt(n.puntaje)})</option>`).join("")}</select>` : ""}
      ${pub && ev.ajustes?.[c.criterio_id] ? `<span class="badge info">ajustado</span>` : ""}</div></header>
      <p class="small">${esc(c.justificacion)}</p>
      ${c.evidencias.map((x) => `<div class="ev ${esc(x.estado)}">${x.estado === "medicion" ? "📏" : x.estado === "no_encontrada" ? "✗" : "✓"} <q>${esc(x.cita)}</q>
        <div class="small muted">${esc(x.fuente)} · ${x.estado === "medicion" ? "medición automática" : x.estado === "no_encontrada" ? "<strong>cita no encontrada en el material</strong>" : `verificada (${esc(x.estado)}) en ${esc(x.ubicacion_verificada)}`}</div></div>`).join("")}
    </div>`).join("")}
  </div>
  <div class="grid g2">
    <div class="card"><h3>Aprendizajes demostrados</h3><ul class="clean">${(r.aprendizajes_demostrados || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul>
      <h3 style="margin-top:12px">Fortalezas</h3><ul class="clean">${(r.fortalezas || []).map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div>
    <div class="card"><h3>Vacíos</h3>${r.vacios?.length ? `<ul class="clean">${r.vacios.map((x) => `<li>${esc(x)}</li>`).join("")}</ul>` : `<p class="muted">Sin vacíos relevantes.</p>`}</div>
  </div>
  <div class="card"><h2>Retroalimentación</h2><p>${esc(r.retroalimentacion)}</p>
    <h3>Recomendaciones</h3><ul class="clean">${(r.recomendaciones || []).map((x) => `<li><strong>${esc(x.accion)}.</strong> ${esc(x.como)}</li>`).join("")}</ul>
    ${r.actividades_fortalecimiento?.length ? `<h3 style="margin-top:12px">Actividades de fortalecimiento</h3><ul class="clean">${r.actividades_fortalecimiento.map((x) => `<li><strong>${esc(x.titulo)}</strong> <span class="badge">${esc(x.competencia_id)}</span> — ${esc(x.descripcion)}</li>`).join("")}</ul>` : ""}
  </div>
  ${doc && ev.estado === "preliminar" ? `<div class="card" id="revision"><h2>Revisión docente</h2>
    <p class="small muted">Puedes cambiar niveles arriba; la nota se recalcula en el servidor. Nota con tus ajustes: <strong id="notaAjustada">${fmt(ev.nota_preliminar)}</strong></p>
    <div class="field"><label>Justificación del ajuste (obligatoria si cambias niveles)</label><textarea id="justif" placeholder="¿Por qué cambias el nivel propuesto?"></textarea></div>
    <div class="field"><label>Comentario para el estudiante (opcional)</label><textarea id="coment"></textarea></div>
    <div class="row"><button class="btn primary" id="btnAprobar">Aprobar y publicar</button><button class="btn" id="btnAjustar" disabled>Publicar con ajustes</button></div></div>` : ""}
  ${doc ? `<div class="card"><details><summary>Trazabilidad técnica</summary><dl class="kv" style="margin-top:10px">
    <dt>Modelo</dt><dd>${esc(ev.trazabilidad.proveedor)} / ${esc(ev.trazabilidad.modelo)}</dd>
    <dt>Parámetros</dt><dd><code>${esc(JSON.stringify(ev.trazabilidad.parametros))}</code></dd>
    <dt>Esquema de salida</dt><dd>${esc(ev.trazabilidad.schema_version)} (validado con Pydantic)</dd>
    <dt>Rúbrica</dt><dd>v${ev.rubrica_version} (id ${ev.rubrica_id})</dd><dt>Verificación</dt><dd>#${ev.trazabilidad.verificacion_id}</dd>
    <dt>SHA-256 entrada</dt><dd><code>${esc(ev.trazabilidad.entrada_sha256)}</code></dd><dt>SHA-256 prompt</dt><dd><code>${esc(ev.trazabilidad.prompt_sha256)}</code></dd>
    <dt>Intentos / duración</dt><dd>${ev.trazabilidad.intentos} · ${ev.trazabilidad.duracion_ms} ms</dd>
    <dt>Tokens</dt><dd>entrada ${ev.trazabilidad.uso_tokens?.entrada ?? "—"} · salida ${ev.trazabilidad.uso_tokens?.salida ?? "—"}</dd>
    <dt>Creada</dt><dd>${fecha(ev.created_at)}</dd>${ev.revisada_at ? `<dt>Revisada</dt><dd>${fecha(ev.revisada_at)} (${esc(ev.decision)})</dd>` : ""}</dl>
    <details style="margin-top:10px"><summary class="small">Respuesta JSON del modelo</summary><pre class="out">${esc(JSON.stringify(ev.respuesta, null, 2))}</pre></details></details></div>` : ""}`;
}

function bindRevision(ev, e) {
  if (!ev || ev.estado !== "preliminar") return;
  const sel = $$(".ajuste");
  const niv = Object.fromEntries(ev.resultado.criterios.map((c) => [c.criterio_id, c.nivel_id]));
  const ajustes = () => Object.fromEntries(sel.filter((s) => s.value !== niv[s.dataset.crit]).map((s) => [s.dataset.crit, s.value]));
  const recalcular = () => {
    let total = 0;
    for (const c of e.rubrica.criterios) {
      const nid = sel.find((s) => s.dataset.crit === c.id)?.value || niv[c.id];
      total += (c.peso / 100) * c.niveles.find((n) => n.id === nid).puntaje;
    }
    $("#notaAjustada").textContent = fmt(Math.round(total * 10 + 1e-9) / 10);
    const hay = Object.keys(ajustes()).length > 0;
    $("#btnAjustar").disabled = !hay;
    $("#btnAprobar").disabled = hay;
  };
  sel.forEach((s) => (s.onchange = recalcular));
  const enviar = async (decision, btn) => {
    busy(btn, true, "Publicando…");
    try {
      const r = await api(`/evaluaciones/${ev.id}/revision`, { method: "POST", body: { decision, ajustes: ajustes(), justificacion: $("#justif").value, comentario: $("#coment").value } });
      toast(`Nota ${fmt(r.nota_final)} publicada`);
      render();
    } catch (er) { toast(er.message, true); busy(btn, false); }
  };
  $("#btnAprobar").onclick = (x) => enviar("aprobada", x.target);
  $("#btnAjustar").onclick = (x) => enviar("ajustada", x.target);
}

/* ---------------------------------------------------------------- revisiones */
route("/revisiones", async () => {
  const pend = await api("/revisiones/pendientes");
  app.innerHTML = `<div class="page-head"><div><h1>Revisiones pendientes</h1><p>Ninguna nota se publica sin tu aprobación o ajuste.</p></div></div>
  <div class="card">${pend.length ? tablaPendientes(pend) : `<div class="empty">No hay evaluaciones pendientes.</div>`}</div>`;
}, "docente");

/* ---------------------------------------------------------------- informes */
route("/informes", async () => {
  const [coh, est] = await Promise.all([api("/cohortes"), api("/usuarios?rol=estudiante")]);
  app.innerHTML = `<div class="page-head"><div><h1>Informes</h1><p>Consolidado por estudiante, corte y laboratorio.</p></div></div>
  <div class="grid g3">
    <div class="card"><h2>Por estudiante</h2><p class="small muted">Informe integrado descargable en PDF.</p>${est.map((s) => `<a class="lab" style="margin-top:8px" href="#/informe/estudiante/${s.id}"><span class="meta"><strong>${esc(s.nombre)}</strong><span class="small muted">${esc(s.email)}</span></span></a>`).join("")}</div>
    <div class="card"><h2>Por corte</h2>${coh.map((c) => `<a class="lab" style="margin-top:8px" href="#/informe/cohorte/${c.id}"><span class="meta"><strong>${esc(c.nombre)}</strong><span class="small muted">${c.laboratorios.length} laboratorios</span></span></a>`).join("")}</div>
    <div class="card"><h2>Por laboratorio</h2>${coh.flatMap((c) => c.laboratorios).map((l) => `<a class="lab" style="margin-top:8px" href="#/informe/laboratorio/${l.id}"><span class="meta"><strong>${esc(l.nombre)}</strong><span class="small muted">${l.entregas} entrega(s)</span></span></a>`).join("")}</div>
  </div>`;
}, "docente");

route("/informe/estudiante/:id", async ({ id, prel }) => {
  const doc = state.user.rol === "docente";
  const incluir = doc && prel === "1";
  const d = await api(`/informes/estudiante/${id}${incluir ? "?preliminares=true" : ""}`);
  app.innerHTML = `
  <div class="crumbs">${doc ? `<a href="#/informes">Informes</a> / ` : ""}Informe integrado</div>
  <div class="page-head"><div><h1>${esc(d.estudiante.nombre)}</h1><p>Informe integrado de aprendizaje · ${incluir ? '<span class="badge warn">incluye notas preliminares</span>' : "solo notas publicadas"}</p></div>
    <div class="row">${doc ? `<a class="btn" href="#/informe/estudiante/${id}${incluir ? "" : "?prel=1"}">${incluir ? "Solo publicadas" : "Incluir preliminares"}</a>` : ""}
    <a class="btn primary" href="/api/informes/estudiante/${id}/pdf${incluir ? "?preliminares=true" : ""}">Descargar PDF</a></div></div>
  <div class="grid g4" style="margin-bottom:16px">
    <div class="card stat"><span class="l">Promedio general</span><span class="v">${fmt(d.promedio_general, 2)}</span><span class="l">${esc(d.nivel_general)}</span></div>
    ${d.cohortes.map((c) => `<div class="card stat"><span class="l">${esc(c.cohorte)}</span><span class="v">${fmt(c.promedio, 2)}</span><span class="l">${c.evaluados}/${c.total} evaluados</span></div>`).join("")}
    <div class="card stat"><span class="l">Progresión</span><span class="v">${d.progresion ? (d.progresion.delta > 0 ? "+" : "") + fmt(d.progresion.delta, 2) : "—"}</span><span class="l">${d.progresion ? esc(d.progresion.tendencia) : "requiere 2 cortes"}</span></div>
  </div>
  <div class="card" style="margin-bottom:16px"><p style="margin:0">${esc(d.resumen)}</p></div>
  <div class="grid g2">
    <div class="card"><h2>Competencias del curso</h2>
      ${d.competencias.length ? d.competencias.map((c) => `<div style="margin:12px 0"><div class="row between"><span><strong>${esc(c.id)}</strong> ${esc(c.nombre)}</span>
        <span class="badge ${c.estado === "alcanzada" ? "ok" : c.estado === "en desarrollo" ? "warn" : "bad"}">${esc(c.estado)} · ${fmt(c.promedio, 2)}</span></div>
        <div class="bar ${c.promedio >= 4 ? "" : c.promedio >= 3 ? "warn" : "bad"}" style="margin-top:6px"><span style="width:${(c.promedio / 5) * 100}%"></span></div>
        <div class="small muted">${Object.entries(c.por_cohorte).map(([k, v]) => `${esc(k)}: ${fmt(v, 2)}`).join(" · ")}</div></div>`).join("") : `<p class="muted">Sin datos.</p>`}
    </div>
    <div class="card"><h2>Plan de fortalecimiento</h2>
      ${d.plan_fortalecimiento.length ? d.plan_fortalecimiento.map((p) => `<div style="margin-bottom:14px"><div class="row"><strong>${esc(p.competencia)}</strong><span class="badge ${p.prioridad === "alta" ? "bad" : "warn"}">prioridad ${esc(p.prioridad)}</span></div>
        ${p.motivo ? `<div class="small muted">${esc(p.motivo)}</div>` : ""}<ul class="clean">${p.actividades.map((a) => `<li><strong>${esc(a.titulo)}:</strong> ${esc(a.descripcion)} <span class="small muted">(${esc(a.origen || "")})</span></li>`).join("")}</ul></div>`).join("")
        : `<p class="muted">Sin brechas: todas las competencias evaluadas están alcanzadas.</p>`}
    </div>
  </div>
  ${d.cohortes.map((c) => `<div class="card" style="margin-top:16px"><h2>${esc(c.cohorte)}</h2><div class="table-wrap"><table><thead><tr><th>Laboratorio</th><th>Estado</th><th class="num">Nota</th><th>Fortalezas</th><th>Por mejorar</th></tr></thead><tbody>
    ${c.laboratorios.map((l) => `<tr ${l.entrega_id ? `class="click" data-href="#/entrega/${l.entrega_id}"` : ""}><td>${esc(l.laboratorio)}</td><td><span class="badge ${l.estado === "publicada" ? "ok" : l.estado === "preliminar" ? "warn" : ""}">${esc(l.estado)}</span></td>
      <td class="num"><strong>${fmt(l.nota)}</strong></td><td class="small">${esc((l.fortalezas || []).slice(0, 2).join("; "))}</td><td class="small">${esc((l.vacios || []).slice(0, 2).join("; "))}</td></tr>`).join("")}
  </tbody></table></div></div>`).join("")}`;
});

route("/informe/cohorte/:id", async ({ id }) => {
  const d = await api(`/informes/cohorte/${id}`);
  const s = d.estadisticas;
  const labs = d.laboratorios.map((l) => l.laboratorio);
  app.innerHTML = `<div class="crumbs"><a href="#/informes">Informes</a></div>
  <div class="page-head"><div><h1>${esc(d.cohorte)}</h1><p>Incluye notas preliminares y publicadas.</p></div></div>
  <div class="grid g4" style="margin-bottom:16px"><div class="card stat"><span class="v">${fmt(s.promedio, 2)}</span><span class="l">promedio</span></div>
    <div class="card stat"><span class="v">${s.n}</span><span class="l">trabajos evaluados</span></div><div class="card stat"><span class="v">${s.aprobados}</span><span class="l">≥ 3,0</span></div>
    <div class="card stat"><span class="v">${fmt(s.desviacion, 2)}</span><span class="l">desviación</span></div></div>
  <div class="card" style="margin-bottom:16px"><h2>Laboratorios</h2><div class="table-wrap"><table><thead><tr><th>Laboratorio</th><th class="num">n</th><th class="num">Promedio</th><th class="num">Mín</th><th class="num">Máx</th><th>Criterio más débil</th></tr></thead><tbody>
    ${d.laboratorios.map((l) => `<tr class="click" data-href="#/informe/laboratorio/${l.laboratorio_id}"><td>${esc(l.laboratorio)}</td><td class="num">${l.n}</td><td class="num">${fmt(l.promedio, 2)}</td><td class="num">${fmt(l.min)}</td><td class="num">${fmt(l.max)}</td>
      <td class="small">${l.criterio_mas_debil ? `${esc(l.criterio_mas_debil.nombre)} (${fmt(l.criterio_mas_debil.promedio, 2)})` : "—"}</td></tr>`).join("")}</tbody></table></div></div>
  <div class="card"><h2>Estudiantes</h2><div class="table-wrap"><table><thead><tr><th>Estudiante</th>${labs.map((l) => `<th class="num" title="${esc(l)}">${esc(l.split(":")[0].slice(0, 14))}</th>`).join("")}<th class="num">Promedio</th></tr></thead><tbody>
    ${d.estudiantes.map((e) => `<tr><td>${esc(e.estudiante)}</td>${labs.map((l) => `<td class="num">${fmt(e.notas[l])}</td>`).join("")}<td class="num"><strong>${fmt(e.promedio, 2)}</strong></td></tr>`).join("") || `<tr><td colspan="9" class="muted">Sin datos</td></tr>`}</tbody></table></div></div>`;
}, "docente");

route("/informe/laboratorio/:id", async ({ id }) => {
  const d = await api(`/informes/laboratorio/${id}`);
  const s = d.estadisticas;
  app.innerHTML = `<div class="crumbs"><a href="#/informes">Informes</a> / ${esc(d.cohorte)}</div>
  <div class="page-head"><div><h1>${esc(d.laboratorio)}</h1><p>Resultados del laboratorio (incluye preliminares).</p></div></div>
  <div class="grid g4" style="margin-bottom:16px"><div class="card stat"><span class="v">${fmt(s.promedio, 2)}</span><span class="l">promedio</span></div>
    <div class="card stat"><span class="v">${s.n}</span><span class="l">evaluados</span></div><div class="card stat"><span class="v">${fmt(s.min)} – ${fmt(s.max)}</span><span class="l">rango</span></div>
    <div class="card stat"><span class="v">${s.aprobados}</span><span class="l">aprobados</span></div></div>
  <div class="grid g2"><div class="card"><h2>Criterios (de más débil a más fuerte)</h2>${d.criterios.map((c) => `<div style="margin:10px 0"><div class="row between"><span>${esc(c.nombre)}</span><strong>${fmt(c.promedio, 2)}</strong></div>
    <div class="bar ${c.promedio >= 4 ? "" : c.promedio >= 3 ? "warn" : "bad"}"><span style="width:${c.promedio * 20}%"></span></div></div>`).join("") || `<p class="muted">Sin datos</p>`}</div>
  <div class="card"><h2>Entregas</h2><table><thead><tr><th>Estudiante</th><th>Estado</th><th class="num">Nota</th><th class="num">Evidencias</th></tr></thead><tbody>
    ${d.entregas.map((e) => `<tr class="click" data-href="#/entrega/${e.entrega_id}"><td>${esc(e.estudiante)}</td><td>${esc(e.estado)}</td><td class="num">${fmt(e.nota)}</td><td class="num">${e.confianza != null ? fmt(e.confianza, 0) + " %" : "—"}</td></tr>`).join("") || `<tr><td colspan="4" class="muted">Sin entregas</td></tr>`}</tbody></table></div></div>`;
}, "docente");

/* ---------------------------------------------------------------- usuarios */
route("/usuarios", async () => {
  const us = await api("/usuarios");
  app.innerHTML = `<div class="page-head"><div><h1>Usuarios</h1><p>Los estudiantes solo ven sus propias entregas y notas publicadas.</p></div></div>
  <div class="grid split-21">
    <div class="card"><table><thead><tr><th>Nombre</th><th>Correo</th><th>Rol</th></tr></thead><tbody>
      ${us.map((u) => `<tr ${u.rol === "estudiante" ? `class="click" data-href="#/informe/estudiante/${u.id}"` : ""}><td>${esc(u.nombre)}</td><td>${esc(u.email)}</td><td><span class="badge ${u.rol === "docente" ? "accent" : ""}">${esc(u.rol)}</span></td></tr>`).join("")}</tbody></table></div>
    <form class="card" id="formU"><h2>Nuevo usuario</h2>
      <div class="field"><label>Nombre</label><input name="nombre" required minlength="3"></div>
      <div class="field"><label>Correo</label><input name="email" type="email" required></div>
      <div class="field"><label>Rol</label><select name="rol"><option value="estudiante">Estudiante</option><option value="docente">Docente</option></select></div>
      <div class="field"><label>Contraseña inicial</label><input name="password" type="password" minlength="10" required><div class="hint">Mínimo 10 caracteres. Se guarda con bcrypt.</div></div>
      <button class="btn primary">Crear</button></form></div>`;
  $("#formU").onsubmit = async (ev) => {
    ev.preventDefault();
    try { await api("/usuarios", { method: "POST", body: Object.fromEntries(new FormData(ev.target)) }); toast("Usuario creado"); render(); } catch (e) { toast(e.message, true); }
  };
}, "docente");

/* ---------------------------------------------------------------- configuración */
route("/config", async () => {
  const c = await api("/config/modelo");
  const a = c.actual;
  const sb = c.sandbox;
  app.innerHTML = `<div class="page-head"><div><h1>Modelo y sandbox</h1><p>Conector configurable: IA local (Ollama) o API remota. Las claves solo se leen de variables de entorno.</p></div></div>
  <div class="grid g2">
    <form class="card" id="formM"><h2>Conector de modelo</h2>
      <div class="field"><label>Proveedor</label><select name="proveedor" id="selProv">
        <option value="mock">Evaluador heurístico de demostración (sin IA, sin costo)</option>
        <option value="ollama">Ollama — modelo local (gratis, privado)</option>
        <option value="gemini">Google Gemini — plan gratuito (sin tarjeta)</option>
        <option value="openai">API compatible con OpenAI (OpenAI, DeepSeek, Groq, Gemini, LM Studio…)</option>
        <option value="anthropic">Anthropic (Claude)</option></select></div>
      <div class="field"><label>Modelo</label><input name="modelo" id="inModelo" value="${esc(a.modelo)}"></div>
      <div class="field"><label>URL base</label><input name="base_url" id="inUrl" value="${esc(a.base_url)}"></div>
      <div class="grid g2"><div class="field"><label>Temperatura</label><input name="temperatura" type="number" step="0.1" min="0" max="1" value="${a.temperatura}"><div class="hint">0 para máxima reproducibilidad.</div></div>
      <div class="field"><label>Semilla</label><input name="seed" type="number" value="${a.seed}"></div></div>
      <p class="small muted">Credenciales en el servidor: Gemini ${c.credenciales.gemini ? "✓" : "✗"} · OpenAI-compatible ${c.credenciales.openai ? "✓" : "✗"} · Anthropic ${c.credenciales.anthropic ? "✓" : "✗"} · modo JSON ${esc(c.openai_json_mode)}</p>
      <div class="row"><button class="btn primary">Guardar</button><button type="button" class="btn" id="btnProbar">Probar conexión</button></div>
      <p class="small" id="probarOut"></p></form>
    <div class="card"><h2>Sandbox de ejecución</h2>
      <dl class="kv"><dt>Modo efectivo</dt><dd><strong>${esc(sb.modo)}</strong></dd><dt>Docker disponible</dt><dd>${sb.docker ? "sí" : "no"}</dd>
        <dt>Namespaces (unshare)</dt><dd>${sb.unshare ? "sí" : "no"}</dd><dt>Tiempo máximo</dt><dd>${sb.limites?.timeout_s} s</dd><dt>Memoria máxima</dt><dd>${sb.limites?.memoria_mb} MB</dd><dt>Red</dt><dd>deshabilitada por defecto</dd></dl>
      <p class="small muted" style="margin-top:10px">docker: contenedor efímero con --network none, sin capacidades y solo lectura. unshare: namespace de red vacío + límites del kernel. rlimit: límites + bloqueo de sockets (aislamiento parcial, se marca en la evaluación).</p></div>
  </div>`;
  $("#selProv").value = a.proveedor;
  $("#selProv").onchange = () => { const d = c.proveedores[$("#selProv").value]; $("#inModelo").value = d.model; $("#inUrl").value = d.base_url; };
  $("#formM").onsubmit = async (ev) => {
    ev.preventDefault();
    const f = Object.fromEntries(new FormData(ev.target));
    f.temperatura = Number(f.temperatura); f.seed = Number(f.seed);
    try { await api("/config/modelo", { method: "PUT", body: f }); toast("Configuración guardada"); } catch (e) { toast(e.message, true); }
  };
  $("#btnProbar").onclick = async (ev) => {
    busy(ev.target, true, "Probando…");
    const r = await api("/config/modelo/probar", { method: "POST" }).catch((e) => ({ ok: false, mensaje: e.message }));
    $("#probarOut").innerHTML = `<span class="badge ${r.ok ? "ok" : "bad"}">${r.ok ? "OK" : "Error"}</span> ${esc(r.mensaje)}`;
    busy(ev.target, false);
  };
}, "docente");

/* ---------------------------------------------------------------- auditoría */
route("/auditoria", async () => {
  const rows = await api("/auditoria?limite=300");
  app.innerHTML = `<div class="page-head"><div><h1>Auditoría</h1><p>Registro inmutable de acciones: cargas, evaluaciones, ajustes, publicaciones y accesos.</p></div></div>
  <div class="card"><div class="table-wrap"><table><thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Entidad</th><th>Detalle</th></tr></thead><tbody>
  ${rows.map((r) => `<tr><td class="small">${fecha(r.fecha)}</td><td>${esc(r.usuario)}</td><td><code>${esc(r.accion)}</code></td><td class="small">${esc(r.entidad)} ${r.entidad_id ?? ""}</td>
    <td class="small mono" style="max-width:420px;word-break:break-word">${esc(JSON.stringify(r.detalle))}</td></tr>`).join("")}</tbody></table></div></div>`;
}, "docente");

render();
