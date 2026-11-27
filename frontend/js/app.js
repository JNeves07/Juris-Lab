/* ==========================================================================
   JurisLab — front-end (sem dependências externas)
   Contrato da API mantido integralmente; apenas a apresentação mudou.
   ========================================================================== */
"use strict";

/* ---------- Utilitários -------------------------------------------------- */
const $ = (seletor, raiz = document) => raiz.querySelector(seletor);
const $$ = (seletor, raiz = document) => Array.from(raiz.querySelectorAll(seletor));

const TIPOS = {
  acordao: "Acórdão",
  decisao_monocratica: "Decisão monocrática",
  sumula: "Súmula",
  sumula_vinculante: "Súmula vinculante",
  repercussao_geral: "Repercussão geral",
  recurso_repetitivo: "Recurso repetitivo",
  iac: "IAC",
  irdr: "IRDR",
  outro: "Outro",
};
const ROTULOS_RELACAO = {
  segue: "segue", cita: "cita", distingue: "distingue", supera: "supera",
  superada_por: "superada por", confirma: "confirma", contraria: "contraria",
};
const STATUS = ["desconhecido", "vigente", "superada", "revogada"];
const ORDENS = ["relevancia", "data_desc", "data_asc"];
const PADROES_ESTADO = {
  q: "", tribunal: [], ramo: "", tipo: "", status: "", relator: "",
  data_ini: "", data_fim: "", ordem: "relevancia", por_pagina: 20,
  pagina: 1, pasta_id: null, tag: null, favoritos: false, busca_id: null,
};
const ROTULOS_CHIP = {
  q: "Busca", tribunal: "Tribunal", ramo: "Ramo", tipo: "Tipo", status: "Vigência",
  relator: "Relator", data_ini: "A partir de", data_fim: "Até",
  ordem: "Ordem", por_pagina: "Página", pasta_id: "Pasta", tag: "Tag",
  favoritos: "Favoritos", busca_id: "Busca salva",
};

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

// Escapa tudo e só devolve como HTML as marcações <mark> geradas pelo backend.
const comMarca = (s) => esc(s)
  .replace(/&lt;mark&gt;/g, "<mark>")
  .replace(/&lt;\/mark&gt;/g, "</mark>");

const fmtData = (d) => (d ? String(d).split("-").reverse().join("/") : "—");
const numeroCurto = (d) => d.numero_processo || d.classe || "s/n";
const fmtNum = (n) => Number(n || 0).toLocaleString("pt-BR");

// Aceita apenas links http(s) para evitar href="javascript:…" vindo da API.
function urlSegura(url) {
  try {
    const u = new URL(url, location.href);
    return ["http:", "https:"].includes(u.protocol) ? u.href : "";
  } catch { return ""; }
}

/* ---------- Estado compartilhado ---------------------------------------- */
const estado = { ...PADROES_ESTADO };
let pastasCache = [];
let buscasCache = [];
let atual = null;            // decisão aberta no painel
let aba = "ementa";          // aba ativa do painel
let ultimoFoco = null;       // foco a restaurar ao fechar o painel
let seqBusca = 0;            // evita respostas antigas sobrescreverem resultados novos

const inteiro = (valor, minimo, maximo, padrao) => {
  const numero = Number.parseInt(valor, 10);
  return Number.isFinite(numero) ? Math.min(maximo, Math.max(minimo, numero)) : padrao;
};
const dataValida = (valor) => /^\d{4}-\d{2}-\d{2}$/.test(String(valor || ""));
const verdadeiro = (valor) => ["1", "true", "sim", "on", "yes"].includes(String(valor || "").toLowerCase());

/* Funções puras: permitem testar a serialização sem navegador. */
function estadoParaParams(entrada = {}) {
  const alvo = { ...PADROES_ESTADO, ...entrada };
  const p = new URLSearchParams();
  const texto = String(alvo.q || "").trim();
  if (texto) p.set("q", texto);

  const tribunais = Array.isArray(alvo.tribunal)
    ? alvo.tribunal
    : alvo.tribunal ? [alvo.tribunal] : [];
  tribunais.forEach((sigla) => {
    const valor = String(sigla || "").trim();
    if (valor) p.append("tribunal", valor);
  });

  if (alvo.ramo) p.set("ramo", String(alvo.ramo));
  if (alvo.tipo) p.set("tipo", String(alvo.tipo));
  if (alvo.status) p.set("status", String(alvo.status));
  if (alvo.relator && String(alvo.relator).trim()) p.set("relator", String(alvo.relator).trim());
  if (dataValida(alvo.data_ini)) p.set("data_ini", String(alvo.data_ini));
  if (dataValida(alvo.data_fim)) p.set("data_fim", String(alvo.data_fim));
  p.set("ordem", ORDENS.includes(alvo.ordem) ? alvo.ordem : "relevancia");
  p.set("por_pagina", String(inteiro(alvo.por_pagina, 1, 100, 20)));
  p.set("pagina", String(inteiro(alvo.pagina, 1, 100_000, 1)));
  const pasta = inteiro(alvo.pasta_id, 1, 1_000_000, null);
  if (pasta) p.set("pasta_id", String(pasta));
  if (alvo.tag) p.set("tag", String(alvo.tag));
  if (alvo.favoritos) p.set("favoritos", "true");
  const busca = inteiro(alvo.busca_id, 1, 1_000_000, null);
  if (busca) p.set("busca_id", String(busca));
  return p;
}

function paramsParaEstado(entrada = {}) {
  const p = entrada instanceof URLSearchParams ? entrada : new URLSearchParams(String(entrada || ""));
  const pasta = p.get("pasta_id");
  const busca = p.get("busca_id");
  const status = p.get("status");
  const ordem = p.get("ordem");
  return {
    ...PADROES_ESTADO,
    q: p.get("q") || "",
    tribunal: p.getAll("tribunal").filter(Boolean),
    ramo: p.get("ramo") || "",
    tipo: p.get("tipo") || "",
    status: status && STATUS.includes(status) ? status : "",
    relator: p.get("relator") || "",
    data_ini: dataValida(p.get("data_ini")) ? p.get("data_ini") : "",
    data_fim: dataValida(p.get("data_fim")) ? p.get("data_fim") : "",
    ordem: ordem && ORDENS.includes(ordem) ? ordem : "relevancia",
    por_pagina: inteiro(p.get("por_pagina"), 1, 100, 20),
    pagina: inteiro(p.get("pagina"), 1, 100_000, 1),
    pasta_id: pasta && /^\d+$/.test(pasta) ? Number(pasta) : null,
    tag: p.get("tag") || "",
    favoritos: verdadeiro(p.get("favoritos")),
    busca_id: busca && /^\d+$/.test(busca) ? Number(busca) : null,
  };
}

function sincronizarEstado() {
  const seletor = $("#fTribunal");
  const tribunal = seletor?.options.length
    ? Array.from(seletor.selectedOptions).map((o) => o.value)
    : estado.tribunal;
  Object.assign(estado, {
    q: $("#q")?.value.trim() || "",
    tribunal,
    ramo: $("#fRamo")?.value || "",
    tipo: $("#fTipo")?.value || "",
    status: $("#fStatus")?.value || "",
    relator: $("#fRelator")?.value.trim() || "",
    data_ini: $("#fIni")?.value || "",
    data_fim: $("#fFim")?.value || "",
    ordem: $("#fOrdem")?.value || "relevancia",
    por_pagina: inteiro($("#fPorPagina")?.value, 1, 100, 20),
  });
  return estado;
}

function aplicarEstado(entrada = {}) {
  const alvo = { ...PADROES_ESTADO, ...entrada };
  const definir = (id, valor) => {
    const elemento = $("#" + id);
    if (elemento) elemento.value = valor ?? "";
  };
  definir("q", alvo.q);
  definir("fRamo", alvo.ramo);
  definir("fTipo", alvo.tipo);
  definir("fStatus", alvo.status);
  definir("fRelator", alvo.relator);
  definir("fIni", alvo.data_ini);
  definir("fFim", alvo.data_fim);
  definir("fOrdem", alvo.ordem);
  definir("fPorPagina", String(alvo.por_pagina));
  Object.assign(estado, alvo);
  selecionarTribunais(alvo.tribunal);
  validarDatas();
  return estado;
}

function selecionarTribunais(desejados = []) {
  const seletor = $("#fTribunal");
  if (!seletor?.options.length) return;
  const alvo = new Set((Array.isArray(desejados) ? desejados : [desejados]).map(String));
  Array.from(seletor.options).forEach((opcao) => { opcao.selected = alvo.has(opcao.value); });
  estado.tribunal = Array.from(seletor.selectedOptions).map((opcao) => opcao.value);
}

function parametrosApi() {
  const p = estadoParaParams(sincronizarEstado());
  p.delete("busca_id");
  return p;
}

function sincronizarUrl() {
  try {
    const consulta = estadoParaParams(sincronizarEstado()).toString();
    const destino = `${location.pathname}${consulta ? `?${consulta}` : ""}${location.hash || ""}`;
    const atualUrl = `${location.pathname}${location.search}${location.hash}`;
    if (destino !== atualUrl) history.replaceState(history.state, "", destino);
  } catch { /* ambientes sem History API continuam funcionando */ }
}

function validarDatas() {
  const ini = $("#fIni")?.value || "";
  const fim = $("#fFim")?.value || "";
  const invalido = Boolean(ini && fim && ini > fim);
  const erro = $("#dataErro");
  if (erro) erro.hidden = !invalido;
  ["fIni", "fFim"].forEach((id) => {
    const campo = $("#" + id);
    if (!campo) return;
    if (invalido) campo.setAttribute("aria-invalid", "true");
    else campo.removeAttribute("aria-invalid");
  });
  return !invalido;
}

if (typeof window !== "undefined") {
  window.__JLS_TEST__ = { estadoParaParams, paramsParaEstado, aplicarEstado, sincronizarEstado };
}

/* ---------- API, erros e toasts ----------------------------------------- */
async function api(url, opcoes = {}) {
  const resposta = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...opcoes,
  });
  const texto = await resposta.text();
  if (!resposta.ok) {
    let detalhe = texto;
    try {
      const corpo = JSON.parse(texto);
      if (corpo.detail) detalhe = corpo.detail;
    } catch { /* corpo não é JSON: usa o texto bruto */ }
    if (typeof detalhe !== "string" || !detalhe) detalhe = resposta.statusText || `Erro ${resposta.status}`;
    throw new Error(detalhe);
  }
  return texto ? JSON.parse(texto) : null;
}

function mensagemErro(erro) {
  const msg = String(erro?.message || erro || "");
  if (/failed to fetch|networkerror|load failed|network/i.test(msg)) {
    return "Não foi possível conectar ao servidor. Verifique sua conexão e tente novamente.";
  }
  if (/não encontrad|not found|404/i.test(msg)) return "Registro não encontrado.";
  if (/422|validation error|value error/i.test(msg)) return "Revise os dados informados e tente novamente.";
  return msg.length > 180 ? `${msg.slice(0, 177)}…` : msg;
}

function toast(mensagem, tipo = "info", desfazer = null) {
  const icones = { info: "i", sucesso: "v", erro: "!" };
  const el = document.createElement("div");
  el.className = `toast toast-${tipo}`;
  el.innerHTML = `
    <span class="toast-ico" aria-hidden="true">${icones[tipo] || icones.info}</span>
    <span>${esc(mensagem)}</span>
    <button class="toast-fechar" type="button" aria-label="Fechar aviso">×</button>`;
  const remover = () => {
    el.classList.add("saindo");
    setTimeout(() => el.remove(), 220);
  };
  if (typeof desfazer === "function") {
    const botao = document.createElement("button");
    botao.type = "button";
    botao.className = "toast-desfazer";
    botao.textContent = "Desfazer";
    botao.addEventListener("click", async () => {
      botao.disabled = true;
      try { await desfazer(); } catch (e) { toast(mensagemErro(e), "erro"); }
      finally { remover(); }
    });
    el.append(botao);
  }
  ($(tipo === "erro" ? "#alertas" : "#toasts") || $("#toasts")).append(el);
  $(".toast-fechar", el).addEventListener("click", remover);
  setTimeout(remover, desfazer ? 8000 : 4500);
}

/* ---------- Parâmetros da busca ----------------------------------------- */
function params() {
  return estadoParaParams(sincronizarEstado());
}

/* ---------- Busca e resultados ------------------------------------------ */
const skeletonCards = () => Array.from({ length: 5 }, () => `
  <div class="result skeleton-card" aria-hidden="true">
    <span class="skeleton sk-titulo"></span><span class="skeleton sk-meta"></span>
    <span class="skeleton sk-linha"></span><span class="skeleton sk-linha sk-linha-curta"></span>
  </div>`).join("");

function estadoVazio() {
  return `<div class="estado-vazio">
    <div class="estado-ico" aria-hidden="true">⌕</div>
    <h3>Nenhuma decisão encontrada</h3>
    <p>Tente termos mais amplos, verifique a grafia ou remova alguns filtros.</p>
    <button class="btn btn-outline" type="button" data-action="limpar">Limpar filtros</button>
  </div>`;
}

function estadoErro(mensagem) {
  return `<div class="estado-erro">
    <div class="estado-ico" aria-hidden="true">!</div>
    <h3>Não foi possível carregar os resultados</h3>
    <p>${esc(mensagem)}</p>
    <button class="btn btn-outline" type="button" data-action="tentar">Tentar novamente</button>
  </div>`;
}

function card(d) {
  const favorito = Boolean(d.favorito);
  const tipo = TIPOS[d.tipo] || d.tipo || "Outro";
  const rotulo = `Abrir decisão ${d.tribunal || ""} ${numeroCurto(d)}`;
  return `<article class="result" data-id="${d.id}">
    <div class="result-topo">
      <button class="result-titulo" type="button" data-action="abrir" data-id="${d.id}"
              aria-label="${esc(rotulo)}">
        <span class="result-id">${esc(d.tribunal)} · ${esc(numeroCurto(d))}</span>
      </button>
      <button class="star ${favorito ? "on" : ""}" type="button" data-action="fav" data-id="${d.id}"
              aria-label="${favorito ? "Remover dos favoritos" : "Adicionar aos favoritos"}"
              aria-pressed="${favorito}" title="${favorito ? "Remover favorito" : "Favoritar"}">
        <span aria-hidden="true">${favorito ? "★" : "☆"}</span>
      </button>
    </div>
    <p class="result-meta">
      <span class="badge">${esc(tipo)}</span>
      ${d.status && d.status !== "desconhecido" ? `<span class="badge ${esc(d.status)}">${esc(d.status)}</span>` : ""}
      ${esc(d.relator || "Relator não informado")} · julgado em ${fmtData(d.data_julgamento)}
    </p>
    <p class="trecho">${comMarca(d.trecho)}</p>
    <button class="btn-link result-abrir" type="button" data-action="abrir" data-id="${d.id}"
            aria-label="${esc(rotulo)}">Abrir decisão</button>
  </article>`;
}

function renderChips() {
  const p = params();
  const html = [];
  for (const [chave, valor] of p.entries()) {
    if (!ROTULOS_CHIP[chave] || (chave === "ordem" && valor === "relevancia")) continue;
    if (chave === "por_pagina" && Number(valor) === 20) continue;
    let exibicao = valor;
    if (chave === "pasta_id") exibicao = pastasCache.find((x) => String(x.id) === String(valor))?.nome || valor;
    if (chave === "favoritos") exibicao = "somente favoritos";
    if (chave === "por_pagina") exibicao = `${valor} por página`;
    if (chave === "busca_id") exibicao = buscasCache.find((b) => String(b.id) === String(valor))?.nome || valor;
    html.push(`<button class="chip-filtro" type="button" data-action="remover-chip"
      data-chave="${chave}" data-valor="${esc(valor)}"
      aria-label="Remover filtro ${esc(ROTULOS_CHIP[chave])}: ${esc(exibicao)}">
      <b>${ROTULOS_CHIP[chave]}:</b> ${esc(exibicao)} <span class="chip-x" aria-hidden="true">×</span>
    </button>`);
  }
  $("#chipsAtivos").innerHTML = html.join("");
}

function marcarBuscaAtiva() { document.body.classList.add("buscando"); }

async function buscar(resetPagina = true) {
  if (resetPagina) estado.pagina = 1;
  sincronizarEstado();
  sincronizarUrl();
  const seq = ++seqBusca;
  const lista = $("#resultados");
  renderChips();

  if (!validarDatas()) {
    lista.setAttribute("aria-busy", "false");
    lista.innerHTML = estadoErro("A data inicial não pode ser posterior à data final.");
    $("#pager").innerHTML = "";
    $("#resumo").textContent = "Revise o período informado.";
    return;
  }

  lista.setAttribute("aria-busy", "true");
  lista.innerHTML = skeletonCards();

  try {
    const r = await api(`/api/busca?${parametrosApi()}`);
    if (seq !== seqBusca) return;

    const total = Number(r.total || 0);
    const aproximado = r.total_truncado ? " (contagem limitada)" : "";
    $("#resumo").textContent = !total ? "Nenhuma decisão encontrada"
      : `${r.total_truncado ? "Mais de " : ""}${fmtNum(total)} ${total === 1 ? "decisão encontrada" : "decisões encontradas"}${aproximado}`;

    const busca = buscasCache.find((b) => b.id === estado.busca_id);
    const pasta = pastasCache.find((p) => p.id === estado.pasta_id);
    $("#escopo").textContent = [
      busca && `Busca salva: ${busca.nome}`,
      estado.favoritos && "Favoritos",
      pasta && `Pasta: ${pasta.nome}`,
      estado.tag && `Tag: ${estado.tag}`,
    ].filter(Boolean).join(" · ");

    lista.innerHTML = r.itens?.length ? r.itens.map(card).join("") : estadoVazio();

    const porPagina = Number(r.por_pagina) || estado.por_pagina || 20;
    const ultimaPagina = Math.max(1, Math.ceil(total / porPagina));
    const proximaPermitida = r.total_truncado || estado.pagina < ultimaPagina;
    const paginaTexto = r.total_truncado
      ? `Página ${estado.pagina} · contagem aproximada`
      : `Página ${estado.pagina} de ${ultimaPagina}`;
    $("#pager").innerHTML = total > porPagina || estado.pagina > 1 ? `
      <button class="btn btn-outline" type="button" data-action="pagina" data-pagina="${estado.pagina - 1}"
              aria-label="Página anterior" ${estado.pagina <= 1 ? "disabled" : ""}>← Anterior</button>
      <span aria-current="page">${paginaTexto}</span>
      <button class="btn btn-outline" type="button" data-action="pagina" data-pagina="${estado.pagina + 1}"
              aria-label="Próxima página" ${proximaPermitida ? "" : "disabled"}>Próxima →</button>` : "";
  } catch (e) {
    if (seq !== seqBusca) return;
    lista.innerHTML = estadoErro(mensagemErro(e));
    $("#pager").innerHTML = "";
    toast(mensagemErro(e), "erro");
  } finally {
    if (seq === seqBusca) lista.setAttribute("aria-busy", "false");
  }
}

async function irParaPagina(p) {
  estado.pagina = p;
  marcarBuscaAtiva();
  await buscar(false);
  $("#resultados .result-titulo")?.focus();
  window.scrollTo({ top: 0 });
}

/* ---------- Hero / estatísticas ----------------------------------------- */
async function carregarEstatisticas() {
  const caixa = $("#estatisticas");
  caixa.setAttribute("aria-busy", "true");
  try {
    const s = await api("/api/estatisticas");
    const tribunais = s.por_tribunal || [];
    const coletas = s.ultima_coleta || [];
    const ultima = coletas[0];
    const maximo = Math.max(1, ...tribunais.map((t) => Number(t.n) || 0));
    const total = Number(s.decisoes);

    caixa.innerHTML = `
      <article class="stat">
        <p class="stat-num">${Number.isFinite(total) && total >= 0 ? fmtNum(total) : "—"}</p>
        <p class="stat-rotulo">Decisões indexadas</p>
      </article>
      <article class="stat">
        <p class="stat-num">${fmtNum(tribunais.length)}</p>
        <p class="stat-rotulo">Tribunais na base</p>
        <div class="barras">
          ${tribunais.slice(0, 4).map((t) => `
            <div class="barra" title="${esc(t.sigla)}: ${fmtNum(t.n)} decisões">
              <em>${esc(t.sigla)}</em>
              <span style="width:${Math.round((Number(t.n) || 0) / maximo * 100)}%"></span>
            </div>`).join("")}
        </div>
      </article>
      <article class="stat">
        <p class="stat-num">${ultima?.finalizada_em ? fmtData(String(ultima.finalizada_em).slice(0, 10)) : "—"}</p>
        <p class="stat-rotulo">Última coleta${ultima?.fonte ? ` · ${esc(ultima.fonte)}` : ""}</p>
        <p class="stat-detalhe">${ultima
          ? `${fmtNum(ultima.inseridas)} inseridas · ${fmtNum(ultima.atualizadas)} atualizadas`
          : "Nenhuma coleta registrada até agora"}</p>
      </article>`;
  } catch {
    caixa.innerHTML = '<p class="stat-erro">Estatísticas indisponíveis no momento.</p>';
  } finally {
    caixa.setAttribute("aria-busy", "false");
  }
}

/* ---------- Coluna lateral ---------------------------------------------- */
async function carregarLaterais() {
  const [tribunais, pastas, tags, buscas] = await Promise.all([
    api("/api/tribunais"), api("/api/pastas"), api("/api/tags"), api("/api/buscas-salvas"),
  ]);
  pastasCache = pastas;
  buscasCache = buscas;

  if (!$("#fTribunal").options.length) {
    const grupos = {};
    tribunais.forEach((t) => (grupos[t.ramo] ||= []).push(t));
    $("#fTribunal").innerHTML = Object.entries(grupos).map(([grupo, lista]) => `
      <optgroup label="${esc(grupo)}">
        ${lista.map((t) => `<option value="${esc(t.sigla)}">${esc(t.sigla)}</option>`).join("")}
      </optgroup>`).join("");
    const ramos = [...new Set(tribunais.map((t) => t.ramo).filter(Boolean))].sort((a, b) => a.localeCompare(b, "pt-BR"));
    $("#fRamo").innerHTML = '<option value="">Todos os ramos</option>'
      + ramos.map((ramo) => `<option value="${esc(ramo)}">${esc(ramo)}</option>`).join("");
  }
  $("#fRamo").value = estado.ramo || "";
  selecionarTribunais(estado.tribunal);

  $("#sideFav").innerHTML = `<li>
    <button class="side-item ${estado.favoritos ? "on" : ""}" type="button" data-action="escopo-fav"
            aria-pressed="${estado.favoritos}"><span><span class="side-ico">★</span> Favoritos</span></button>
  </li>`;

  $("#sidePastas").innerHTML = pastas.map((p) => `
    <li><button class="side-item ${estado.pasta_id === p.id ? "on" : ""}" type="button"
      data-action="escopo-pasta" data-id="${p.id}" aria-pressed="${estado.pasta_id === p.id}">
      <span>Pasta: ${esc(p.nome)}</span><span class="n">${fmtNum(p.total)}</span></button></li>`).join("")
    || '<li class="side-vazio">Nenhuma pasta criada.</li>';

  $("#sideTags").innerHTML = tags.map((t) => `
    <li><button class="side-item ${estado.tag === t.nome ? "on" : ""}" type="button"
      data-action="escopo-tag" data-tag="${esc(t.nome)}" aria-pressed="${estado.tag === t.nome}">
      <span># ${esc(t.nome)}</span><span class="n">${fmtNum(t.total)}</span></button></li>`).join("")
    || '<li class="side-vazio">Nenhuma tag criada.</li>';

  $("#sideBuscas").innerHTML = buscas.map((b) => `
    <li><button class="side-item" type="button" data-action="aplicar-busca" data-id="${b.id}">
      <span>Busca: ${esc(b.nome)}</span></button>
      <button class="side-item-excluir" type="button" data-action="busca-del" data-id="${b.id}"
              aria-label="Excluir busca salva ${esc(b.nome)}" title="Excluir busca">×</button></li>`).join("")
    || '<li class="side-vazio">Nenhuma busca salva.</li>';
}

function recarregarLaterais() { carregarLaterais().catch((e) => toast(mensagemErro(e), "erro")); }

/* ---------- Ações de filtros, pastas e buscas salvas --------------------- */
function filtrarPasta(id) {
  estado.pasta_id = estado.pasta_id === id ? null : id;
  marcarBuscaAtiva();
  recarregarLaterais();
  buscar();
}

function filtrarTag(nome) {
  estado.tag = estado.tag === nome ? null : nome;
  marcarBuscaAtiva();
  recarregarLaterais();
  buscar();
}

function alternarFavoritos() {
  estado.favoritos = !estado.favoritos;
  marcarBuscaAtiva();
  recarregarLaterais();
  buscar();
}

function removerChip(chave, valor) {
  const alvo = paramsParaEstado(params());
  if (chave === "q") alvo.q = "";
  else if (chave === "tribunal") alvo.tribunal = alvo.tribunal.filter((s) => s !== valor);
  else if (["tipo", "status", "ramo", "relator", "data_ini", "data_fim"].includes(chave)) alvo[chave] = "";
  else if (chave === "ordem") alvo.ordem = "relevancia";
  else if (chave === "por_pagina") alvo.por_pagina = 20;
  else if (chave === "pasta_id") alvo.pasta_id = null;
  else if (chave === "tag") alvo.tag = null;
  else if (chave === "favoritos") alvo.favoritos = false;
  else if (chave === "busca_id") alvo.busca_id = null;
  alvo.pagina = 1;
  aplicarEstado(alvo);
  marcarBuscaAtiva();
  recarregarLaterais();
  buscar();
}

function limparFiltros() {
  aplicarEstado(PADROES_ESTADO);
  document.body.classList.remove("buscando");
  recarregarLaterais();
  buscar();
}

async function alternarFormulario(botao, formId, abrir) {
  const form = $("#" + formId);
  form.hidden = !abrir;
  botao.setAttribute("aria-expanded", String(abrir));
  if (abrir) {
    $("input", form)?.focus();
  } else {
    const campo = $("input", form);
    if (campo) campo.value = "";
  }
}

async function criarPasta() {
  const nome = $("#nomePasta").value.trim();
  if (!nome) return;
  try {
    await api("/api/pastas", { method: "POST", body: JSON.stringify({ nome }) });
    await alternarFormulario($("#btnNovaPasta"), "formNovaPasta", false);
    recarregarLaterais();
    toast("Pasta criada com sucesso.", "sucesso");
  } catch (e) { toast(mensagemErro(e), "erro"); }
}

async function salvarBusca() {
  const nome = $("#nomeBusca").value.trim();
  if (!nome) return;
  const p = params();
  p.delete("pagina");
  p.delete("busca_id");
  const filtros = {
    ...Object.fromEntries([...p.entries()].filter(([chave]) => chave !== "q" && chave !== "tribunal")),
    tribunal: p.getAll("tribunal"),
  };
  try {
    const salva = await api("/api/buscas-salvas", {
      method: "POST",
      body: JSON.stringify({ nome, consulta: $("#q").value, filtros }),
    });
    await alternarFormulario($("#btnSalvarBusca"), "formNovaBusca", false);
    estado.busca_id = salva?.id || null;
    recarregarLaterais();
    buscar();
    toast("Busca salva na sua lista.", "sucesso");
  } catch (e) { toast(mensagemErro(e), "erro"); }
}

function aplicarBusca(b) {
  if (!b || !b.id) return toast("Esta busca salva não está mais disponível.", "erro");
  const f = b.filtros || {};
  aplicarEstado({
    q: b.consulta || "",
    tribunal: Array.isArray(f.tribunal) ? f.tribunal : f.tribunal ? [f.tribunal] : [],
    ramo: f.ramo || "",
    tipo: f.tipo || "",
    status: f.status || "",
    relator: f.relator || "",
    data_ini: f.data_ini || "",
    data_fim: f.data_fim || "",
    ordem: f.ordem || "relevancia",
    por_pagina: inteiro(f.por_pagina, 1, 100, 20),
    pagina: 1,
    pasta_id: f.pasta_id ? Number(f.pasta_id) : null,
    tag: f.tag || "",
    favoritos: f.favoritos === "true" || f.favoritos === true,
    busca_id: b.id,
  });
  marcarBuscaAtiva();
  recarregarLaterais();
  buscar();
  toast(`Busca “${b.nome}” aplicada.`);
}

async function excluirBusca(id) {
  const busca = buscasCache.find((b) => b.id === Number(id));
  if (!busca) return;
  try {
    await api(`/api/buscas-salvas/${id}`, { method: "DELETE" });
    if (estado.busca_id === busca.id) estado.busca_id = null;
    recarregarLaterais();
    buscar();
    toast("Busca salva removida.", "sucesso", async () => {
      await api("/api/buscas-salvas", {
        method: "POST",
        body: JSON.stringify({ nome: busca.nome, consulta: busca.consulta, filtros: busca.filtros }),
      });
      recarregarLaterais();
      toast("Busca salva restaurada.", "sucesso");
    });
  } catch (e) { toast(mensagemErro(e), "erro"); }
}

/* ---------- Favoritos (cartão e painel) --------------------------------- */
async function favoritar(id, botao) {
  const ligado = !botao.classList.contains("on");
  const pintar = (on) => {
    botao.classList.toggle("on", on);
    botao.innerHTML = `<span aria-hidden="true">${on ? "★" : "☆"}</span>`;
    botao.setAttribute("aria-pressed", String(on));
    botao.setAttribute("aria-label", on ? "Remover dos favoritos" : "Adicionar aos favoritos");
  };
  pintar(ligado);
  try {
    await api(`/api/decisoes/${id}/favorito`, { method: ligado ? "PUT" : "DELETE" });
    toast(ligado ? "Decisão adicionada aos favoritos." : "Decisão removida dos favoritos.", "sucesso");
    if (estado.favoritos) buscar(false);
  } catch (e) {
    pintar(!ligado); // desfaz a mudança otimista
    toast(mensagemErro(e), "erro");
  }
}

async function favoritarPainel() {
  if (!atual) return;
  const ligado = !atual.favorito;
  try {
    await api(`/api/decisoes/${atual.id}/favorito`, { method: ligado ? "PUT" : "DELETE" });
    atual.favorito = ligado;
    desenharPainel();
    buscar(false);
    toast(ligado ? "Decisão adicionada aos favoritos." : "Decisão removida dos favoritos.", "sucesso");
  } catch (e) { toast(mensagemErro(e), "erro"); }
}

/* ---------- Painel de leitura ------------------------------------------- */
function painelAberto() { return $("#painel").classList.contains("on"); }

function definirInerte(ativo) {
  [".topbar", "#conteudo"].forEach((seletor) => {
    const elemento = $(seletor);
    if (!elemento) return;
    if (ativo) elemento.setAttribute("inert", "");
    else elemento.removeAttribute("inert");
  });
}

async function abrir(id) {
  try {
    atual = await api(`/api/decisoes/${id}`);
    aba = "ementa";
    abrirPainel();
  } catch (e) { toast(mensagemErro(e), "erro"); }
}

function abrirPainel() {
  if (!painelAberto()) ultimoFoco = document.activeElement;
  const painel = $("#painel");
  painel.classList.add("on");
  painel.setAttribute("aria-hidden", "false");
  $("#overlayPainel").hidden = false;
  document.body.classList.add("modal-aberto");
  definirInerte(true);
  desenharPainel();
  requestAnimationFrame(() => $("#btnFecharPainel")?.focus());
}

function fecharPainel() {
  const painel = $("#painel");
  if (!painelAberto()) return;
  painel.classList.remove("on");
  painel.setAttribute("aria-hidden", "true");
  $("#overlayPainel").hidden = true;
  document.body.classList.remove("modal-aberto");
  definirInerte(false);
  atual = null;
  ultimoFoco?.focus?.();
}

function desenharPainel() {
  if (!atual) return;
  const d = atual;
  const legislativa = (d.legislacao_citada || []).map((x) => `<span class="chip">${esc(x)}</span>`).join("");
  const qtdNotas = (d.anotacoes || []).length;
  const qtdRelacoes = (d.relacoes || []).length;
  const fonte = urlSegura(d.fonte_url);

  const corpo = {
    ementa: `
      ${d.tese ? `<h4>Tese</h4><div class="texto">${esc(d.tese)}</div>` : ""}
      <h4>Ementa</h4><div class="texto">${esc(d.ementa || "—")}</div>
      ${legislativa ? `<h4>Legislação citada</h4>${legislativa}` : ""}`,
    teor: `<div class="texto">${esc(d.inteiro_teor || "Inteiro teor não disponível.")}</div>`,
    organizar: organizarHtml(d),
    notas: notasHtml(d),
    relacoes: relacoesHtml(d),
  }[aba];

  const abas = [
    ["ementa", "Ementa"], ["teor", "Inteiro teor"], ["organizar", "Pastas e tags"],
    ["notas", `Anotações (${qtdNotas})`], ["relacoes", `Relações (${qtdRelacoes})`],
  ];

  $("#painelIn").innerHTML = `
    <div class="painel-cabecalho">
      <div class="painel-acoes">
        <button class="btn btn-ghost" type="button" id="btnFecharPainel" data-action="fechar-painel">✕ Fechar</button>
        <div class="painel-acoes-direita">
          <button class="btn btn-outline" type="button" data-action="copiar-numero">Copiar nº do processo</button>
          <button class="btn btn-outline" type="button" data-action="fav-painel"
                  aria-pressed="${Boolean(d.favorito)}">${d.favorito ? "★ Favorito" : "☆ Favoritar"}</button>
        </div>
      </div>
      <h2 class="painel-titulo" id="painelTitulo">${esc(d.tribunal)} · ${esc(numeroCurto(d))}</h2>
      <div class="painel-meta">
        <span class="badge">${esc(TIPOS[d.tipo] || d.tipo || "Outro")}</span>
        ${d.status && d.status !== "desconhecido" ? `<span class="badge ${esc(d.status)}">${esc(d.status)}</span>` : ""}
        ${esc(d.orgao_julgador || "")} · Relator: ${esc(d.relator || "—")}
      </div>
      <div class="painel-sub">
        Julgado em ${fmtData(d.data_julgamento)} · Publicado em ${fmtData(d.data_publicacao)}
        ${fonte ? ` · <a href="${esc(fonte)}" target="_blank" rel="noopener noreferrer">fonte original ↗</a>` : ""}
      </div>
      <div class="painel-sub">
        Origem: ${esc(d.fonte)} · coletado em ${fmtData(String(d.coletado_em || "").slice(0, 10))}
        ${d.numero_cnj ? ` · CNJ ${esc(d.numero_cnj)}` : ""}
      </div>
      <div class="painel-linha">
        <label for="selStatus">Vigência</label>
        <select id="selStatus" data-action="mudar-status">
          ${STATUS.map((s) => `<option value="${s}" ${s === d.status ? "selected" : ""}>${s}</option>`).join("")}
        </select>
      </div>
      <div class="tabs" role="tablist" aria-label="Seções da decisão">
        ${abas.map(([chave, titulo]) => `
          <button class="aba ${aba === chave ? "on" : ""}" type="button" role="tab"
                  id="aba-${chave}" aria-controls="painelTab" aria-selected="${aba === chave}"
                  tabindex="${aba === chave ? 0 : -1}" data-action="aba" data-aba="${chave}">${titulo}</button>`).join("")}
      </div>
    </div>
    <div class="tabcontent" id="painelTab" role="tabpanel" aria-labelledby="aba-${aba}">${corpo}</div>`;
}

function trocarAba(chave) {
  aba = chave;
  desenharPainel();
  $(`#aba-${chave}`)?.focus();
}

async function copiarTexto(texto, mensagemOk, mensagemErro) {
  let campo = null;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(texto);
    } else {
      campo = document.createElement("textarea");
      campo.value = texto;
      campo.style.position = "fixed";
      campo.style.opacity = "0";
      document.body.append(campo);
      campo.select();
      if (!document.execCommand("copy")) throw new Error("Cópia não autorizada");
    }
    toast(mensagemOk, "sucesso");
  } catch { toast(mensagemErro, "erro"); }
  finally { campo?.remove(); }
}

async function copiarNumero() {
  if (!atual) return;
  await copiarTexto(
    numeroCurto(atual),
    "Número do processo copiado.",
    "Não foi possível copiar o número do processo.",
  );
}

async function copiarLink() {
  sincronizarEstado();
  sincronizarUrl();
  await copiarTexto(
    location.href,
    "Link da busca copiado.",
    "Não foi possível copiar o link. Copie o endereço da barra do navegador.",
  );
}

async function exportar(formato) {
  try {
    const p = estadoParaParams(sincronizarEstado());
    p.delete("pagina");
    p.delete("por_pagina");
    p.delete("busca_id");
    p.set("formato", formato);
    const resposta = await fetch(`/api/busca/export?${p}`, {
      headers: { Accept: formato === "json" ? "application/json" : "text/csv" },
    });
    if (!resposta.ok) throw new Error((await resposta.text()).slice(0, 180));
    const blob = await resposta.blob();
    const nome = /filename="([^"]+)"/.exec(resposta.headers.get("content-disposition") || "")?.[1]
      || `jurislab.${formato}`;
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = nome;
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    toast(`Exportação ${formato.toUpperCase()} iniciada.`, "sucesso");
  } catch (e) { toast(mensagemErro(e), "erro"); }
}

async function mudarStatus(valor) {
  if (!atual) return;
  try {
    await api(`/api/decisoes/${atual.id}/status`, {
      method: "PUT", body: JSON.stringify({ status: valor }),
    });
    atual.status = valor;
    toast("Vigência atualizada.", "sucesso");
  } catch (e) {
    toast(mensagemErro(e), "erro");
    desenharPainel();
  }
}

/* Aba: pastas e tags */
function organizarHtml(d) {
  return `<h4>Pastas</h4>
    ${(d.pastas || []).map((p) => `<span class="chip">${esc(p.nome)}
      <button type="button" data-action="pasta-del" data-id="${p.id}" aria-label="Remover da pasta ${esc(p.nome)}">×</button></span>`).join("")
      || '<p class="dica">Nenhuma pasta.</p>'}
    <div class="linha">
      <label class="sr-only" for="selPasta">Adicionar a uma pasta</label>
      <select id="selPasta">
        <option value="">Adicionar a uma pasta…</option>
        ${pastasCache.map((p) => `<option value="${p.id}">${esc(p.nome)}</option>`).join("")}
      </select>
      <button class="btn btn-outline" type="button" data-action="pasta-add">Adicionar</button>
    </div>
    <h4>Tags</h4>
    ${(d.tags || []).map((t) => `<span class="chip"># ${esc(t.nome)}
      <button type="button" data-action="tag-del" data-id="${t.id}" aria-label="Remover tag ${esc(t.nome)}">×</button></span>`).join("")
      || '<p class="dica">Nenhuma tag.</p>'}
    <div class="linha">
      <label class="sr-only" for="novaTag">Nova tag</label>
      <input type="text" id="novaTag" placeholder="Nova tag (ex.: dano moral)">
      <button class="btn btn-outline" type="button" data-action="tag-add">Adicionar</button>
    </div>`;
}

async function recarregarDecisao() {
  if (!atual) return;
  atual = await api(`/api/decisoes/${atual.id}`);
  desenharPainel();
  recarregarLaterais();
}

async function executar(acao, mensagem, mensagemFalha, desfazer = null) {
  try {
    await acao();
    await recarregarDecisao();
    if (typeof desfazer === "function") {
      toast(mensagem, "sucesso", async () => {
        await desfazer();
        await recarregarDecisao();
      });
    } else {
      toast(mensagem, "sucesso");
    }
  } catch (e) { toast(mensagemFalha || mensagemErro(e), "erro"); }
}

function adicionarPasta() {
  const id = $("#selPasta")?.value;
  if (id) executar(() => api(`/api/decisoes/${atual.id}/pastas/${id}`, { method: "PUT" }), "Decisão adicionada à pasta.");
}
function removerPasta(id) {
  if (!atual) return;
  const decisaoId = atual.id;
  const pasta = (atual.pastas || []).find((p) => p.id === Number(id));
  executar(
    () => api(`/api/decisoes/${decisaoId}/pastas/${id}`, { method: "DELETE" }),
    "Decisão removida da pasta.",
    undefined,
    async () => {
      if (!pasta) return;
      await api(`/api/decisoes/${decisaoId}/pastas/${pasta.id}`, { method: "PUT" });
      toast("Pasta restaurada.", "sucesso");
    },
  );
}
function adicionarTag() {
  const nome = $("#novaTag")?.value.trim();
  if (nome) executar(() => api(`/api/decisoes/${atual.id}/tags`, {
    method: "PUT", body: JSON.stringify({ nome }),
  }), "Tag adicionada.");
}
function removerTag(id) {
  if (!atual) return;
  const decisaoId = atual.id;
  const tag = (atual.tags || []).find((t) => t.id === Number(id));
  executar(
    () => api(`/api/decisoes/${decisaoId}/tags/${id}`, { method: "DELETE" }),
    "Tag removida.", undefined,
    async () => {
      if (!tag) return;
      await api(`/api/decisoes/${decisaoId}/tags`, {
        method: "PUT", body: JSON.stringify({ nome: tag.nome }),
      });
      toast("Tag restaurada.", "sucesso");
    },
  );
}

/* Aba: anotações */
function notasHtml(d) {
  const notas = (d.anotacoes || []).map((a) => `<div class="nota">
    ${a.trecho ? `<div class="dica">“${esc(a.trecho)}”</div>` : ""}
    <div>${esc(a.texto)}</div>
    <div class="dica">${fmtData(String(a.criada_em || "").slice(0, 10))}
      <button class="acao-perigo" type="button" data-action="nota-del" data-id="${a.id}">apagar</button>
    </div>
  </div>`).join("");
  return `${notas || '<p class="dica">Sem anotações.</p>'}
    <h4>Nova anotação</h4>
    <div class="campo">
      <label for="notaTrecho">Trecho destacado (opcional)</label>
      <input type="text" id="notaTrecho" placeholder="Copie aqui o trecho de interesse">
    </div>
    <div class="campo">
      <label for="notaTexto">Anotação</label>
      <textarea id="notaTexto" rows="4" placeholder="Escreva sua observação…"></textarea>
    </div>
    <div class="linha"><button class="btn btn-primary" type="button" data-action="nota-add">Salvar anotação</button></div>`;
}

function adicionarNota() {
  const texto = $("#notaTexto")?.value.trim();
  if (!texto) return toast("Escreva o texto da anotação antes de salvar.", "erro");
  executar(() => api(`/api/decisoes/${atual.id}/anotacoes`, {
    method: "POST",
    body: JSON.stringify({ texto, trecho: $("#notaTrecho").value.trim() || null }),
  }), "Anotação salva.");
}
function removerNota(id) {
  const decisaoId = atual?.id;
  const nota = (atual?.anotacoes || []).find((a) => a.id === Number(id));
  executar(
    () => api(`/api/anotacoes/${id}`, { method: "DELETE" }),
    "Anotação removida.", undefined,
    async () => {
      if (!nota || !decisaoId) return;
      await api(`/api/decisoes/${decisaoId}/anotacoes`, {
        method: "POST",
        body: JSON.stringify({ texto: nota.texto, trecho: nota.trecho || null }),
      });
      toast("Anotação restaurada.", "sucesso");
    },
  );
}

/* Aba: relações */
function relacoesHtml(d) {
  const relacoes = (d.relacoes || []).map((r) => {
    const rotulo = ROTULOS_RELACAO[r.tipo] || r.tipo;
    const frase = r.direcao === "saida"
      ? `Esta decisão ${rotulo}`
      : (r.tipo === "supera" ? "É superada por" : `É alvo de “${rotulo}” em`);
    return `<div class="nota">
      <b>${esc(frase)}</b>
      <button class="btn-link" type="button" data-action="abrir-relacao" data-id="${r.outra_id}">
        ${esc(r.tribunal)} ${esc(numeroCurto(r))}
      </button>
      ${r.nota ? `<div class="dica">${esc(r.nota)}</div>` : ""}
      <div class="dica"><button class="acao-perigo" type="button" data-action="rel-del" data-id="${r.id}">remover</button></div>
    </div>`;
  }).join("");

  return `${relacoes || '<p class="dica">Sem relações.</p>'}
    <h4>Nova relação</h4>
    <div class="campo">
      <label for="relTipo">Tipo de relação</label>
      <select id="relTipo">${Object.entries(ROTULOS_RELACAO).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
    </div>
    <div class="campo">
      <label for="relDestino">ID da decisão de destino</label>
      <input type="text" id="relDestino" inputmode="numeric" placeholder="Ex.: 1234">
    </div>
    <div class="campo">
      <label for="relNota">Nota (opcional)</label>
      <input type="text" id="relNota" placeholder="Observação sobre a relação">
    </div>
    <div class="linha"><button class="btn btn-outline" type="button" data-action="rel-add">Relacionar</button></div>
    <p class="dica">O ID aparece na URL da API (/api/decisoes/ID).</p>`;
}

function adicionarRelacao() {
  const destino = Number.parseInt($("#relDestino")?.value, 10);
  if (!destino) return toast("Informe o ID da decisão de destino.", "erro");
  const corpo = {
    destino_id: destino,
    tipo: $("#relTipo").value,
    nota: $("#relNota").value || null,
  };
  executar(() => api(`/api/decisoes/${atual.id}/relacoes`, {
    method: "POST", body: JSON.stringify(corpo),
  }), "Relação criada.", "Decisão de destino não encontrada.");
}
function removerRelacao(id) {
  const decisaoId = atual?.id;
  const relacao = (atual?.relacoes || []).find((r) => r.id === Number(id));
  executar(
    () => api(`/api/relacoes/${id}`, { method: "DELETE" }),
    "Relação removida.", undefined,
    async () => {
      if (!relacao || !decisaoId) return;
      await api(`/api/decisoes/${decisaoId}/relacoes`, {
        method: "POST",
        body: JSON.stringify({
          destino_id: relacao.outra_id, tipo: relacao.tipo, nota: relacao.nota || null,
        }),
      });
      toast("Relação restaurada.", "sucesso");
    },
  );
}

/* ---------- Drawer de filtros (telas pequenas) -------------------------- */
function abrirFiltros() {
  const botao = $("#btnFiltros");
  const gaveta = $("#filtros");
  gaveta.classList.add("aberto");
  gaveta.setAttribute("role", "dialog");
  gaveta.setAttribute("aria-modal", "true");
  gaveta.setAttribute("aria-labelledby", "filtrosTitulo");
  gaveta.removeAttribute("aria-label");
  $("#overlayFiltros").hidden = false;
  document.body.classList.add("drawer-aberto");
  definirInerte(true);
  botao.setAttribute("aria-expanded", "true");
  botao.setAttribute("aria-label", "Fechar filtros");
  requestAnimationFrame(() => $("#fTribunal")?.focus());
}

function fecharFiltros() {
  const botao = $("#btnFiltros");
  const gaveta = $("#filtros");
  if (!gaveta.classList.contains("aberto")) return;
  gaveta.classList.remove("aberto");
  gaveta.removeAttribute("role");
  gaveta.removeAttribute("aria-modal");
  gaveta.removeAttribute("aria-labelledby");
  gaveta.setAttribute("aria-label", "Filtros e coleções");
  $("#overlayFiltros").hidden = true;
  document.body.classList.remove("drawer-aberto");
  definirInerte(false);
  botao.setAttribute("aria-expanded", "false");
  botao.setAttribute("aria-label", "Abrir filtros");
  botao.focus();
}

/* ---------- Delegação de eventos ---------------------------------------- */
document.addEventListener("click", (evento) => {
  const alvo = evento.target.closest("[data-action]");
  if (!alvo) return;
  const acao = alvo.dataset.action;

  switch (acao) {
    case "abrir":
      if (evento.target.closest(".star")) return;
      abrir(Number(alvo.dataset.id)); break;
    case "fav": favoritar(Number(alvo.dataset.id), alvo); break;
    case "pagina": irParaPagina(Number(alvo.dataset.pagina)); break;
    case "remover-chip": removerChip(alvo.dataset.chave, alvo.dataset.valor); break;
    case "limpar": limparFiltros(); break;
    case "fechar-filtros": fecharFiltros(); break;
    case "copiar-link": copiarLink(); break;
    case "exportar-csv": exportar("csv"); break;
    case "exportar-json": exportar("json"); break;
    case "tentar": marcarBuscaAtiva(); buscar(); break;
    case "escopo-fav": alternarFavoritos(); break;
    case "escopo-pasta": filtrarPasta(Number(alvo.dataset.id)); break;
    case "escopo-tag": filtrarTag(alvo.dataset.tag); break;
    case "aplicar-busca": aplicarBusca(buscasCache.find((b) => b.id === Number(alvo.dataset.id)) || {}); break;
    case "busca-del": excluirBusca(Number(alvo.dataset.id)); break;
    case "alternar-pasta": alternarFormulario(alvo, "formNovaPasta", alvo.getAttribute("aria-expanded") !== "true"); break;
    case "cancelar-pasta": alternarFormulario($("#btnNovaPasta"), "formNovaPasta", false); break;
    case "alternar-busca": alternarFormulario(alvo, "formNovaBusca", alvo.getAttribute("aria-expanded") !== "true"); break;
    case "cancelar-busca": alternarFormulario($("#btnSalvarBusca"), "formNovaBusca", false); break;

    case "fechar-painel": fecharPainel(); break;
    case "copiar-numero": copiarNumero(); break;
    case "fav-painel": favoritarPainel(); break;
    case "aba": trocarAba(alvo.dataset.aba); break;
    case "pasta-add": adicionarPasta(); break;
    case "pasta-del": removerPasta(Number(alvo.dataset.id)); break;
    case "tag-add": adicionarTag(); break;
    case "tag-del": removerTag(Number(alvo.dataset.id)); break;
    case "nota-add": adicionarNota(); break;
    case "nota-del": removerNota(Number(alvo.dataset.id)); break;
    case "rel-add": adicionarRelacao(); break;
    case "rel-del": removerRelacao(Number(alvo.dataset.id)); break;
    case "abrir-relacao": abrir(Number(alvo.dataset.id)); break;
    default: break;
  }
});

$("#painelIn").addEventListener("change", (e) => {
  if (e.target.id === "selStatus") mudarStatus(e.target.value);
});

$("#painelIn").addEventListener("keydown", (e) => {
  if (e.target.matches('[role="tab"]') && ["ArrowLeft", "ArrowRight"].includes(e.key)) {
    const abas = $$('[role="tab"]', $("#painelIn"));
    const atualIdx = abas.indexOf(e.target);
    const prox = (atualIdx + (e.key === "ArrowRight" ? 1 : -1) + abas.length) % abas.length;
    trocarAba(abas[prox].dataset.aba);
    return;
  }
  if (e.key !== "Enter" || !e.target.matches("input")) return;
  if (e.target.id === "novaTag") adicionarTag();
  else if (["relDestino", "relNota"].includes(e.target.id)) adicionarRelacao();
  else if (e.target.id === "notaTrecho") $("#notaTexto")?.focus();
});

$("#formBusca").addEventListener("submit", (e) => {
  e.preventDefault();
  marcarBuscaAtiva();
  buscar();
});
$("#formNovaPasta").addEventListener("submit", (e) => { e.preventDefault(); criarPasta(); });
$("#formNovaBusca").addEventListener("submit", (e) => { e.preventDefault(); salvarBusca(); });

["fTribunal", "fRamo", "fTipo", "fStatus", "fOrdem", "fPorPagina", "fIni", "fFim"].forEach((id) => {
  $("#" + id).addEventListener("change", () => {
    validarDatas();
    marcarBuscaAtiva();
    buscar();
  });
});
$("#fRelator").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); marcarBuscaAtiva(); buscar(); }
});

$("#btnFiltros").addEventListener("click", () => {
  if ($("#filtros").classList.contains("aberto")) fecharFiltros(); else abrirFiltros();
});
$("#overlayFiltros").addEventListener("click", fecharFiltros);
$("#overlayPainel").addEventListener("click", fecharPainel);

function prenderFoco(evento, dialogo) {
  const seletor = 'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';
  const focaveis = $$(seletor, dialogo).filter((el) => el.getClientRects().length > 0);
  if (!focaveis.length) return;
  const primeiro = focaveis[0];
  const ultimo = focaveis[focaveis.length - 1];
  if (evento.shiftKey && document.activeElement === primeiro) {
    evento.preventDefault();
    ultimo.focus();
  } else if (!evento.shiftKey && document.activeElement === ultimo) {
    evento.preventDefault();
    primeiro.focus();
  }
}

document.addEventListener("keydown", (e) => {
  const filtrosAbertos = $("#filtros").classList.contains("aberto");
  if (e.key === "Escape") {
    if (painelAberto()) fecharPainel();
    else if (filtrosAbertos) fecharFiltros();
    return;
  }

  // Atalho "/": foca a busca quando o usuário não está digitando.
  if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey && !painelAberto() && !filtrosAbertos) {
    const alvo = e.target;
    if (alvo instanceof HTMLElement && (alvo.matches("input, textarea, select") || alvo.isContentEditable)) return;
    e.preventDefault();
    $("#q").focus();
    $("#q").select();
    return;
  }

  // Mantém o foco dentro do diálogo ativo (aria-modal).
  if (e.key === "Tab") {
    if (painelAberto()) prenderFoco(e, $("#painel"));
    else if (filtrosAbertos) prenderFoco(e, $("#filtros"));
  }
});

/* ---------- Inicialização ----------------------------------------------- */
aplicarEstado(paramsParaEstado(new URLSearchParams(location.search)));
carregarEstatisticas();
carregarLaterais()
  .catch((e) => toast(mensagemErro(e), "erro"))
  .finally(() => buscar(false));
