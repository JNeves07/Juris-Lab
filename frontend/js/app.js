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
const ROTULOS_CHIP = {
  q: "Busca", tribunal: "Tribunal", tipo: "Tipo", status: "Vigência",
  relator: "Relator", data_ini: "A partir de", data_fim: "Até",
  ordem: "Ordem", pasta_id: "Pasta", tag: "Tag", favoritos: "Favoritos",
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
const estado = { pagina: 1, pasta_id: null, tag: null, favoritos: false };
let pastasCache = [];
let buscasCache = [];
let atual = null;            // decisão aberta no painel
let aba = "ementa";          // aba ativa do painel
let ultimoFoco = null;       // foco a restaurar ao fechar o painel
let seqBusca = 0;            // evita respostas antigas sobrescreverem resultados novos

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

function toast(mensagem, tipo = "info") {
  const icones = { info: "i", sucesso: "✓", erro: "!" };
  const el = document.createElement("div");
  el.className = `toast toast-${tipo}`;
  el.innerHTML = `
    <span class="toast-ico" aria-hidden="true">${icones[tipo] || icones.info}</span>
    <span>${esc(mensagem)}</span>
    <button class="toast-fechar" type="button" data-action="fechar-toast" aria-label="Fechar aviso">×</button>`;
  $("#toasts").append(el);
  const remover = () => {
    el.classList.add("saindo");
    setTimeout(() => el.remove(), 220);
  };
  $(".toast-fechar", el).addEventListener("click", remover);
  setTimeout(remover, 4500);
}

/* ---------- Parâmetros da busca ----------------------------------------- */
function params() {
  const p = new URLSearchParams();
  if ($("#q").value.trim()) p.set("q", $("#q").value.trim());
  Array.from($("#fTribunal").selectedOptions).forEach((o) => p.append("tribunal", o.value));
  if ($("#fTipo").value) p.set("tipo", $("#fTipo").value);
  if ($("#fStatus").value) p.set("status", $("#fStatus").value);
  if ($("#fRelator").value.trim()) p.set("relator", $("#fRelator").value.trim());
  if ($("#fIni").value) p.set("data_ini", $("#fIni").value);
  if ($("#fFim").value) p.set("data_fim", $("#fFim").value);
  p.set("ordem", $("#fOrdem").value);
  p.set("pagina", estado.pagina);
  if (estado.pasta_id) p.set("pasta_id", estado.pasta_id);
  if (estado.tag) p.set("tag", estado.tag);
  if (estado.favoritos) p.set("favoritos", "true");
  return p;
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
  return `<article class="result" data-action="abrir" data-id="${d.id}" tabindex="0" role="button"
                 aria-label="Abrir decisão ${esc(d.tribunal)} ${esc(numeroCurto(d))}">
    <div class="result-topo">
      <p class="result-id">${esc(d.tribunal)} · ${esc(numeroCurto(d))}</p>
      <button class="star ${favorito ? "on" : ""}" type="button" data-action="fav" data-id="${d.id}"
              aria-label="${favorito ? "Remover dos favoritos" : "Adicionar aos favoritos"}"
              aria-pressed="${favorito}" title="Favoritar">${favorito ? "★" : "☆"}</button>
    </div>
    <p class="result-meta">
      <span class="badge">${esc(tipo)}</span>
      ${d.status && d.status !== "desconhecido" ? `<span class="badge ${esc(d.status)}">${esc(d.status)}</span>` : ""}
      ${esc(d.relator || "Relator não informado")} · julgado em ${fmtData(d.data_julgamento)}
    </p>
    <p class="trecho">${comMarca(d.trecho)}</p>
  </article>`;
}

function renderChips() {
  const p = params();
  const html = [];
  for (const [chave, valor] of p.entries()) {
    if (!ROTULOS_CHIP[chave] || (chave === "ordem" && valor === "relevancia")) continue;
    let exibicao = valor;
    if (chave === "pasta_id") exibicao = pastasCache.find((x) => String(x.id) === String(valor))?.nome || valor;
    if (chave === "favoritos") exibicao = "somente favoritos";
    html.push(`<button class="chip-filtro" type="button" data-action="remover-chip"
      data-chave="${chave}" data-valor="${esc(valor)}">
      <b>${ROTULOS_CHIP[chave]}:</b> ${esc(exibicao)} <span class="chip-x" aria-hidden="true">×</span>
    </button>`);
  }
  $("#chipsAtivos").innerHTML = html.join("");
}

function marcarBuscaAtiva() { document.body.classList.add("buscando"); }

async function buscar(resetPagina = true) {
  if (resetPagina) estado.pagina = 1;
  const seq = ++seqBusca;
  const lista = $("#resultados");
  renderChips();
  lista.setAttribute("aria-busy", "true");
  lista.innerHTML = skeletonCards();

  try {
    const r = await api(`/api/busca?${params()}`);
    if (seq !== seqBusca) return;

    const total = Number(r.total || 0);
    $("#resumo").textContent = !total ? "Nenhuma decisão encontrada"
      : `${r.total_truncado ? "Mais de " : ""}${fmtNum(total)} ${total === 1 ? "decisão encontrada" : "decisões encontradas"}`;

    const pasta = pastasCache.find((p) => p.id === estado.pasta_id);
    $("#escopo").textContent = [
      estado.favoritos && "Favoritos",
      pasta && `Pasta: ${pasta.nome}`,
      estado.tag && `Tag: ${estado.tag}`,
    ].filter(Boolean).join(" · ");

    lista.innerHTML = r.itens?.length ? r.itens.map(card).join("") : estadoVazio();

    const ultimaPagina = Math.max(1, Math.ceil(total / (r.por_pagina || 20)));
    $("#pager").innerHTML = total > r.por_pagina ? `
      <button class="btn btn-outline" type="button" data-action="pagina" data-pagina="${estado.pagina - 1}"
              ${estado.pagina <= 1 ? "disabled" : ""}>← Anterior</button>
      <span>Página ${estado.pagina} de ${r.total_truncado ? "…" : ultimaPagina}</span>
      <button class="btn btn-outline" type="button" data-action="pagina" data-pagina="${estado.pagina + 1}"
              ${estado.pagina >= ultimaPagina ? "disabled" : ""}>Próxima →</button>` : "";
  } catch (e) {
    if (seq !== seqBusca) return;
    lista.innerHTML = estadoErro(mensagemErro(e));
    $("#pager").innerHTML = "";
    toast(mensagemErro(e), "erro");
  } finally {
    if (seq === seqBusca) lista.setAttribute("aria-busy", "false");
  }
}

function irParaPagina(p) {
  estado.pagina = p;
  marcarBuscaAtiva();
  buscar(false);
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
  }

  $("#sideFav").innerHTML = `<li>
    <button class="side-item ${estado.favoritos ? "on" : ""}" type="button" data-action="escopo-fav"
            aria-pressed="${estado.favoritos}"><span><span class="side-ico">★</span> Favoritos</span></button>
  </li>`;

  $("#sidePastas").innerHTML = pastas.map((p) => `
    <li><button class="side-item ${estado.pasta_id === p.id ? "on" : ""}" type="button"
      data-action="escopo-pasta" data-id="${p.id}" aria-pressed="${estado.pasta_id === p.id}">
      <span>📁 ${esc(p.nome)}</span><span class="n">${fmtNum(p.total)}</span></button></li>`).join("")
    || '<li class="side-vazio">Nenhuma pasta criada.</li>';

  $("#sideTags").innerHTML = tags.map((t) => `
    <li><button class="side-item ${estado.tag === t.nome ? "on" : ""}" type="button"
      data-action="escopo-tag" data-tag="${esc(t.nome)}" aria-pressed="${estado.tag === t.nome}">
      <span># ${esc(t.nome)}</span><span class="n">${fmtNum(t.total)}</span></button></li>`).join("")
    || '<li class="side-vazio">Nenhuma tag criada.</li>';

  $("#sideBuscas").innerHTML = buscas.map((b) => `
    <li><button class="side-item" type="button" data-action="aplicar-busca" data-id="${b.id}">
      <span>🔎 ${esc(b.nome)}</span></button>
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
  if (chave === "q") $("#q").value = "";
  else if (chave === "tribunal") {
    const opcao = $("#fTribunal").querySelector(`option[value="${CSS.escape(valor)}"]`);
    if (opcao) opcao.selected = false;
  } else if (["tipo", "status", "ordem", "relator", "data_ini", "data_fim"].includes(chave)) {
    $("#" + chave).value = chave === "ordem" ? "relevancia" : "";
  } else if (chave === "pasta_id") estado.pasta_id = null;
  else if (chave === "tag") estado.tag = null;
  else if (chave === "favoritos") estado.favoritos = false;
  marcarBuscaAtiva();
  recarregarLaterais();
  buscar();
}

function limparFiltros() {
  $("#q").value = "";
  ["fTipo", "fStatus", "fRelator", "fIni", "fFim"].forEach((id) => { $("#" + id).value = ""; });
  $$("#fTribunal option").forEach((o) => { o.selected = false; });
  $("#fOrdem").value = "relevancia";
  Object.assign(estado, { pasta_id: null, tag: null, favoritos: false });
  document.body.classList.remove("buscando");
  recarregarLaterais();
  buscar();
}

async function alternarFormulario(botao, formId, abrir) {
  const form = $("#" + formId);
  form.hidden = abrir;
  botao.setAttribute("aria-expanded", String(abrir));
  if (abrir) {
    $("input", form)?.focus();
  } else {
    $("input", form).value = "";
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
  const filtros = {
    ...Object.fromEntries([...p.entries()].filter(([chave]) => chave !== "q" && chave !== "tribunal")),
    tribunal: p.getAll("tribunal"),
  };
  try {
    await api("/api/buscas-salvas", {
      method: "POST",
      body: JSON.stringify({ nome, consulta: $("#q").value, filtros }),
    });
    await alternarFormulario($("#btnSalvarBusca"), "formNovaBusca", false);
    recarregarLaterais();
    toast("Busca salva na sua lista.", "sucesso");
  } catch (e) { toast(mensagemErro(e), "erro"); }
}

function aplicarBusca(b) {
  if (!b || !b.id) return toast("Esta busca salva não está mais disponível.", "erro");
  $("#q").value = b.consulta || "";
  const f = b.filtros || {};
  $("#fTipo").value = f.tipo || "";
  $("#fStatus").value = f.status || "";
  $("#fRelator").value = f.relator || "";
  $("#fIni").value = f.data_ini || "";
  $("#fFim").value = f.data_fim || "";
  $("#fOrdem").value = f.ordem || "relevancia";
  const tribunais = Array.isArray(f.tribunal) ? f.tribunal : f.tribunal ? [f.tribunal] : [];
  $$("#fTribunal option").forEach((o) => { o.selected = tribunais.includes(o.value); });
  estado.pasta_id = f.pasta_id ? Number(f.pasta_id) : null;
  estado.tag = f.tag || null;
  estado.favoritos = f.favoritos === "true" || f.favoritos === true;
  marcarBuscaAtiva();
  buscar();
  recarregarLaterais();
  toast(`Busca “${b.nome}” aplicada.`);
}

async function excluirBusca(id) {
  try {
    await api(`/api/buscas-salvas/${id}`, { method: "DELETE" });
    recarregarLaterais();
    toast("Busca salva removida.", "sucesso");
  } catch (e) { toast(mensagemErro(e), "erro"); }
}

/* ---------- Favoritos (cartão e painel) --------------------------------- */
async function favoritar(id, botao) {
  const ligado = !botao.classList.contains("on");
  const pintar = (on) => {
    botao.classList.toggle("on", on);
    botao.textContent = on ? "★" : "☆";
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

async function copiarNumero() {
  if (!atual) return;
  const numero = numeroCurto(atual);
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(numero);
    } else {
      const campo = document.createElement("textarea");
      campo.value = numero;
      campo.style.position = "fixed";
      campo.style.opacity = "0";
      document.body.append(campo);
      campo.select();
      document.execCommand("copy");
      campo.remove();
    }
    toast("Número do processo copiado.", "sucesso");
  } catch { toast("Não foi possível copiar o número do processo.", "erro"); }
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

async function executar(acao, mensagem, mensagemFalha) {
  try { await acao(); await recarregarDecisao(); toast(mensagem, "sucesso"); }
  catch (e) { toast(mensagemFalha || mensagemErro(e), "erro"); }
}

function adicionarPasta() {
  const id = $("#selPasta")?.value;
  if (id) executar(() => api(`/api/decisoes/${atual.id}/pastas/${id}`, { method: "PUT" }), "Decisão adicionada à pasta.");
}
function removerPasta(id) {
  executar(() => api(`/api/decisoes/${atual.id}/pastas/${id}`, { method: "DELETE" }), "Decisão removida da pasta.");
}
function adicionarTag() {
  const nome = $("#novaTag")?.value.trim();
  if (nome) executar(() => api(`/api/decisoes/${atual.id}/tags`, {
    method: "PUT", body: JSON.stringify({ nome }),
  }), "Tag adicionada.");
}
function removerTag(id) {
  executar(() => api(`/api/decisoes/${atual.id}/tags/${id}`, { method: "DELETE" }), "Tag removida.");
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
  executar(() => api(`/api/anotacoes/${id}`, { method: "DELETE" }), "Anotação removida.");
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
  executar(() => api(`/api/relacoes/${id}`, { method: "DELETE" }), "Relação removida.");
}

/* ---------- Drawer de filtros (mobile) ---------------------------------- */
function abrirFiltros() {
  const botao = $("#btnFiltros");
  $("#filtros").classList.add("aberto");
  $("#overlayFiltros").hidden = false;
  document.body.classList.add("drawer-aberto");
  botao.setAttribute("aria-expanded", "true");
  botao.setAttribute("aria-label", "Fechar filtros");
  $("#fTribunal")?.focus();
}

function fecharFiltros() {
  const botao = $("#btnFiltros");
  if (!$("#filtros").classList.contains("aberto")) return;
  $("#filtros").classList.remove("aberto");
  $("#overlayFiltros").hidden = true;
  document.body.classList.remove("drawer-aberto");
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

$("#resultados").addEventListener("keydown", (e) => {
  if (e.target.matches(".result") && (e.key === "Enter" || e.key === " ")) {
    e.preventDefault();
    abrir(Number(e.target.dataset.id));
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

["fTribunal", "fTipo", "fStatus", "fOrdem", "fIni", "fFim"].forEach((id) => {
  $("#" + id).addEventListener("change", () => { marcarBuscaAtiva(); buscar(); });
});
$("#fRelator").addEventListener("keydown", (e) => {
  if (e.key === "Enter") { e.preventDefault(); marcarBuscaAtiva(); buscar(); }
});

$("#btnFiltros").addEventListener("click", () => {
  if ($("#filtros").classList.contains("aberto")) fecharFiltros(); else abrirFiltros();
});
$("#overlayFiltros").addEventListener("click", fecharFiltros);
$("#overlayPainel").addEventListener("click", fecharPainel);

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape") {
    if (painelAberto()) fecharPainel();
    else if ($("#filtros").classList.contains("aberto")) fecharFiltros();
    return;
  }

  // Atalho "/": foca a busca quando o usuário não está digitando.
  if (e.key === "/" && !e.ctrlKey && !e.metaKey && !e.altKey && !painelAberto()) {
    const alvo = e.target;
    if (alvo instanceof HTMLElement && (alvo.matches("input, textarea, select") || alvo.isContentEditable)) return;
    e.preventDefault();
    $("#q").focus();
    $("#q").select();
    return;
  }

  // Mantém o foco dentro do diálogo (aria-modal).
  if (e.key === "Tab" && painelAberto()) {
    const focaveis = $$('a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])', $("#painel"));
    if (!focaveis.length) return;
    const primeiro = focaveis[0];
    const ultimo = focaveis[focaveis.length - 1];
    if (e.shiftKey && document.activeElement === primeiro) { e.preventDefault(); ultimo.focus(); }
    else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primeiro.focus(); }
  }
});

/* ---------- Inicialização ----------------------------------------------- */
carregarEstatisticas();
carregarLaterais()
  .catch((e) => toast(mensagemErro(e), "erro"))
  .finally(() => buscar(false));
