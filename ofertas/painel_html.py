"""A página HTML do painel de controle (servida por painel.py)."""

PAGINA = r"""<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Bot de Ofertas — Painel</title>
<style>
  :root{
    --bg:#0f1216; --card:#171b22; --card2:#1e232c; --bd:#2a303b; --tx:#e7ebf0;
    --mut:#95a0b0; --ac:#ff6a3d; --ac2:#ff8a63; --ok:#25c281; --warn:#e0b341; --err:#e8574a;
  }
  @media (prefers-color-scheme:light){
    :root{ --bg:#f2f4f7; --card:#fff; --card2:#f7f9fb; --bd:#dde2e9; --tx:#1b2230;
           --mut:#5a6472; --ac:#f2542d; --ac2:#e0431c; }
  }
  *{box-sizing:border-box}
  body{margin:0;font-family:'Segoe UI',system-ui,sans-serif;background:var(--bg);color:var(--tx);
       line-height:1.5;font-size:15px}
  .wrap{max-width:820px;margin:0 auto;padding:20px 16px 60px}
  header{display:flex;align-items:center;gap:14px;flex-wrap:wrap;margin:8px 0 22px}
  header h1{font-size:20px;margin:0;font-weight:700}
  header h1 .em{font-size:22px}
  .pill{display:inline-flex;align-items:center;gap:7px;font-size:13px;font-weight:600;
        padding:5px 12px;border-radius:99px;background:var(--card2);border:1px solid var(--bd)}
  .dot{width:9px;height:9px;border-radius:99px;background:var(--mut)}
  .dot.on{background:var(--ok);box-shadow:0 0 0 3px rgba(37,194,129,.2)}
  .grow{flex:1}
  button{font:inherit;cursor:pointer;border:0;border-radius:9px;padding:10px 16px;font-weight:600;
         background:var(--card2);color:var(--tx);border:1px solid var(--bd);transition:.15s}
  button:hover{border-color:var(--ac)}
  button:disabled{opacity:.5;cursor:not-allowed}
  button.pri{background:var(--ac);color:#fff;border-color:var(--ac)}
  button.pri:hover{background:var(--ac2)}
  button.stop{background:var(--err);color:#fff;border-color:var(--err)}
  .card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:18px 18px;
        margin-bottom:16px}
  .card h2{font-size:15px;margin:0 0 14px;display:flex;align-items:center;gap:8px}
  .card h2 .n{width:22px;height:22px;border-radius:99px;background:var(--ac);color:#fff;font-size:13px;
              display:grid;place-items:center;font-weight:700}
  .grp{font-size:12px;text-transform:uppercase;letter-spacing:.5px;color:var(--mut);
       margin:16px 0 8px;font-weight:700}
  .grp:first-of-type{margin-top:0}
  .fld{margin-bottom:12px}
  .fld label{display:flex;align-items:center;gap:8px;font-weight:600;font-size:13.5px;margin-bottom:4px}
  .fld .tick{font-size:12px}
  .fld input{width:100%;padding:9px 11px;border-radius:8px;border:1px solid var(--bd);
             background:var(--bg);color:var(--tx);font:inherit}
  .fld input:focus{outline:0;border-color:var(--ac)}
  .fld .help{font-size:12.5px;color:var(--mut);margin-top:3px}
  .row{display:flex;gap:10px;flex-wrap:wrap;align-items:center}
  .log{background:#0a0c10;color:#cdd6e0;font-family:'Cascadia Code',Consolas,monospace;font-size:12.5px;
       border-radius:9px;padding:12px;height:230px;overflow:auto;white-space:pre-wrap;border:1px solid var(--bd)}
  @media (prefers-color-scheme:light){.log{background:#12151b;color:#cdd6e0}}
  .muted{color:var(--mut);font-size:13px}
  .toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--ok);color:#fff;
         padding:10px 18px;border-radius:10px;font-weight:600;opacity:0;transition:.3s;pointer-events:none}
  .toast.show{opacity:1}
  .toast.err{background:var(--err)}
  .ids{margin-top:10px}
  .idbtn{display:block;width:100%;text-align:left;margin-top:6px}
  .nichos-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px}
  .nicho{display:flex;align-items:center;gap:9px;padding:10px 12px;border:1px solid var(--bd);
         border-radius:10px;background:var(--bg);cursor:pointer;user-select:none;transition:.12s}
  .nicho:hover{border-color:var(--ac)}
  .nicho.on{border-color:var(--ac);background:color-mix(in srgb,var(--ac) 14%,transparent)}
  .nicho .emo{font-size:19px}
  .nicho .nm{font-size:13.5px;font-weight:600}
  .nicho .ck{margin-left:auto;font-size:13px;color:var(--ac);opacity:0}
  .nicho.on .ck{opacity:1}
  .hide{display:none}
  textarea{width:100%;padding:9px 11px;border-radius:8px;border:1px solid var(--bd);
           background:var(--bg);color:var(--tx);font:inherit;resize:vertical}
  textarea:focus{outline:0;border-color:var(--ac)}
  .row2{display:flex;gap:12px;flex-wrap:wrap}
  .canal{display:flex;align-items:center;gap:12px;flex-wrap:wrap;padding:12px 14px;margin-bottom:8px;
         border:1px solid var(--bd);border-radius:12px;background:var(--bg)}
  .canal.off{opacity:.55}
  .canal .emo{font-size:24px}
  .canal .info{flex:1;min-width:180px}
  .canal .nm{font-weight:700}
  .canal .sub{font-size:12.5px;color:var(--mut)}
  .canal .acoes{display:flex;gap:6px;flex-wrap:wrap}
  .canal .acoes button{padding:6px 10px;font-size:13px}
  .badge{display:inline-block;font-size:11.5px;padding:2px 8px;border-radius:99px;margin:2px 4px 0 0;
         background:var(--card2);border:1px solid var(--bd)}
  .form-canal{margin-top:16px;padding:16px;border:1px dashed var(--ac);border-radius:12px}
  .form-canal h3{margin:0 0 12px;font-size:15px}
  a{color:var(--ac2)}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1><span class="em">🔥</span> Bot de Ofertas</h1>
    <span class="grow"></span>
    <span class="pill"><span class="dot" id="dot"></span><span id="stt">verificando…</span></span>
    <button class="pri" id="btnBot" onclick="toggleBot()">Ligar bot</button>
  </header>

  <!-- 1. Configuração -->
  <div class="card">
    <h2><span class="n">1</span> Configuração</h2>
    <div id="campos"></div>
    <div class="row" style="margin-top:14px">
      <button class="pri" onclick="salvar()">💾 Salvar</button>
      <button onclick="detectarIds()">🔎 Detectar IDs do Telegram</button>
      <span class="muted" id="salvoMsg"></span>
    </div>
    <div class="ids hide" id="idsBox"></div>
  </div>

  <!-- Canais -->
  <div class="card">
    <h2><span class="n">📢</span> Canais</h2>
    <p class="muted" style="margin:-6px 0 12px">
      Cada canal do Telegram recebe só as ofertas do <b>seu nicho</b>. O mesmo bot posta em todos.
      Antes de criar: adicione o bot como <b>administrador</b> do canal (com permissão de publicar).
    </p>
    <div id="listaCanais">carregando…</div>
    <div class="row" style="margin-top:12px">
      <button class="pri" onclick="novoCanal()">➕ Novo canal</button>
      <button class="hide" id="btnReiniciar" onclick="reiniciarBot()">🔄 Reiniciar bot para aplicar</button>
    </div>

    <div class="form-canal hide" id="formCanal">
      <h3 id="fcTitulo">Novo canal</h3>
      <div class="row2">
        <div class="fld" style="flex:0 0 90px"><label>Emoji</label><input id="c_emoji" maxlength="4" value="📢"></div>
        <div class="fld" style="flex:1"><label>Nome do canal</label><input id="c_nome" placeholder="ex: Perfumes"></div>
      </div>
      <div class="fld">
        <label>ID do canal no Telegram</label>
        <div class="row">
          <input id="c_chat" placeholder="-1001234567890 ou @nomedocanal" style="flex:1">
          <button onclick="detectarIds('#idsBoxCanal')">🔎 Detectar canais</button>
        </div>
        <div class="help">Para o bot enxergar o canal: poste qualquer coisa nele (ou encaminhe um post ao bot) e clique em Detectar.</div>
        <div class="ids hide" id="idsBoxCanal"></div>
      </div>
      <div class="fld">
        <label>Nichos <span class="muted">(escolha um ou mais; ou nenhum e use só palavras-chave)</span></label>
        <div class="nichos-grid" id="nichosGrid"></div>
      </div>
      <div class="fld">
        <label>Palavras-chave próprias <span class="muted">(opcional)</span></label>
        <textarea id="c_palavras" rows="2" placeholder="separe por vírgula. ex: bicicleta, capacete ciclista"></textarea>
        <div class="help">Servem para <b>buscar</b> ofertas e para <b>conferir</b> que o produto é do nicho. É assim que você cria um nicho novo.</div>
      </div>
      <div class="fld">
        <label>Nunca postar títulos com <span class="muted">(opcional)</span></label>
        <textarea id="c_excluir" rows="2" placeholder="separe por vírgula. ex: infantil, capinha"></textarea>
      </div>
      <div class="row2">
        <div class="fld" style="flex:1"><label>Desconto mínimo % <span class="muted">(vazio = padrão)</span></label><input id="c_desc" type="number" min="0" max="90"></div>
        <div class="fld" style="flex:1"><label>Posts por rodada <span class="muted">(vazio = padrão)</span></label><input id="c_max" type="number" min="1" max="20"></div>
      </div>
      <div class="row2">
        <div class="fld" style="flex:1"><label>Etiqueta do ML só deste canal <span class="muted">(opcional)</span></label><input id="c_mletq" placeholder="ex: automotivo"></div>
        <div class="fld" style="flex:1"><label>Tag da Amazon só deste canal <span class="muted">(opcional)</span></label><input id="c_amztag" placeholder="ex: seusite-auto-20"></div>
      </div>
      <div class="help" style="margin:-6px 0 14px">
        Com etiqueta/tag própria, o painel de afiliados do ML e da Amazon mostra cliques e comissões de cada canal
        <b>em separado</b> — assim você descobre qual nicho rende mais. Crie antes: no ML em Linkbuilder → “Etiqueta em uso”;
        na Amazon em Associados → Gerenciar IDs de rastreamento. Vazio = usa a padrão.
      </div>
      <div class="row">
        <button class="pri" onclick="salvarCanal()">💾 Salvar canal</button>
        <button onclick="fecharForm()">Cancelar</button>
      </div>
    </div>
  </div>

  <!-- Execução automática -->
  <div class="card">
    <h2><span class="n">🚀</span> Execução automática</h2>
    <p class="muted" style="margin:-6px 0 12px">
      Liga o bot sozinho quando você entra no Windows, <b>sem janela</b>, e reinicia se ele cair.
      Com isso ativo você não precisa deixar o painel aberto: use-o só para configurar.
    </p>
    <div class="row">
      <button id="btnAuto" onclick="alternarAuto()">…</button>
      <button id="btnAutoAgora" class="hide" onclick="iniciarAgora()">▶️ Iniciar agora em segundo plano</button>
    </div>
    <p class="muted" style="margin:10px 0 0">
      Dica: em Configurações → Sistema → Energia, deixe “Suspender” em <b>Nunca</b>. PC dormindo não posta.
    </p>
  </div>

  <!-- 2. Instalação e testes -->
  <div class="card">
    <h2><span class="n">2</span> Instalação e testes</h2>
    <div class="row">
      <button onclick="acao('instalar-navegador')" id="a_nav">⬇️ Instalar navegador</button>
      <button onclick="acao('ml-login')" id="a_ml">🔑 Login Mercado Livre</button>
      <button onclick="acao('testar-ml')">🧪 Testar ML</button>
      <button onclick="acao('testar-shopee')">🧪 Testar Shopee</button>
      <button onclick="acao('testar-amazon')">🧪 Testar Amazon</button>
    </div>
    <p class="muted" style="margin:10px 0 6px">Saída:</p>
    <div class="log" id="logAcao">—</div>
  </div>

  <!-- 3. Bot -->
  <div class="card">
    <h2><span class="n">3</span> Bot ao vivo</h2>
    <div class="log" id="logBot">O bot está desligado. Configure acima e clique em “Ligar bot”.</div>
  </div>

  <p class="muted" style="text-align:center">
    Roda tudo no seu PC. Feche a janela preta para desligar o painel.
  </p>
</div>
<div class="toast" id="toast"></div>

<script>
const __TOKEN="__TOKEN_PAINEL__";
const __fetch=window.fetch.bind(window);
window.fetch=(u,o={})=>__fetch(u,{...o,headers:{...(o.headers||{}),"X-Painel-Token":__TOKEN}});
const $ = s => document.querySelector(s);
let CFG = {}, statusAtual = {};

const CAMPOS = [
  ["TELEGRAM_BOT_TOKEN","Token do bot","Telegram",true,"Crie no @BotFather com /newbot e cole aqui."],
  ["TELEGRAM_OWNER_ID","Seu user ID","Telegram",false,"Use “Detectar IDs” depois de salvar o token."],
  ["ML_ETIQUETA","Etiqueta do afiliado","Mercado Livre",false,"A “Etiqueta em uso” do Linkbuilder."],
  ["AMAZON_TAG","Tag de associado","Amazon",false,"Sua tag do Amazon Associados (ex: seunome-20)."],
  ["AMAZON_CREDENTIAL_ID","Creators API — ID","Amazon",false,"Opcional (busca automática oficial)."],
  ["AMAZON_CREDENTIAL_SECRET","Creators API — Secret","Amazon",true,"Opcional. Aparece só uma vez."],
  ["SHOPEE_APP_ID","App ID","Shopee",false,"Painel de afiliados > “Abrir API”."],
  ["SHOPEE_APP_SECRET","App Secret","Shopee",true,"Painel de afiliados > “Abrir API”."],
];

function montarCampos(){
  let html = "", grupo = "";
  for(const [k,rot,grp,seg,ajuda] of CAMPOS){
    if(grp!==grupo){ html += `<div class="grp">${grp}</div>`; grupo = grp; }
    const set = CFG[k+"__set"];
    const tick = set ? `<span class="tick" style="color:var(--ok)">✓ preenchido</span>` : "";
    const ph = seg && set ? "•••••• (preenchido — deixe em branco para manter)" : "";
    html += `<div class="fld">
      <label>${rot} ${tick}</label>
      <input id="f_${k}" type="${seg?'password':'text'}" placeholder="${ph}" value="${seg?'':(CFG[k]||'')}">
      <div class="help">${ajuda}</div></div>`;
  }
  $("#campos").innerHTML = html;
}

async function carregarCfg(){ CFG = await (await fetch("/api/config")).json(); montarCampos(); }

async function salvar(){
  const body = {};
  for(const [k] of CAMPOS){ body[k] = $("#f_"+k).value.trim(); }
  await fetch("/api/config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
  toast("Configuração salva!");
  await carregarCfg(); atualizar();
}

async function detectarIds(sel){
  const doCanal = typeof sel === "string";   // chamado de dentro do formulário de canal
  const box = $(doCanal ? sel : "#idsBox"); box.classList.remove("hide");
  box.innerHTML = `<p class="muted">Consultando o Telegram…</p>`;
  const r = await (await fetch("/api/detectar-ids",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"})).json();
  if(r.erro){ box.innerHTML = `<p class="muted" style="color:var(--warn)">${r.erro}</p>`; return; }
  if(r.vazio){
    box.innerHTML = `<p class="muted">Nada encontrado ainda. No Telegram: mande <b>/start</b> e <b>/id</b> para o
      bot, e <b>encaminhe um post do canal</b> para ele. Depois clique de novo.</p>`; return;
  }
  let h = "";
  if(!doCanal && r.pessoas.length){ h += `<p class="muted">Clique no <b>seu usuário</b> (define o dono):</p>`;
    for(const p of r.pessoas) h += `<button class="idbtn" onclick="setId('TELEGRAM_OWNER_ID','${p.id}')">👤 ${esc(p.nome)} — <code>${p.id}</code></button>`; }
  if(doCanal){
    if(!r.canais.length) h = `<p class="muted">Nenhum canal visto ainda. Poste algo no canal (com o bot como admin) e clique de novo.</p>`;
    else { h += `<p class="muted" style="margin-top:8px">Clique no canal:</p>`;
      for(const c of r.canais) h += `<button class="idbtn" onclick="$('#c_chat').value='${c.id}'">📢 ${esc(c.nome)} — <code>${c.id}</code></button>`; }
  }
  box.innerHTML = h || `<p class="muted">Nada novo para escolher.</p>`;
}
function setId(campo,val){ $("#f_"+campo).value = val; toast("Preenchido — não esqueça de salvar."); }
function esc(s){ return String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }

async function acao(nome){
  const r = await (await fetch("/api/acao",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({nome})})).json();
  if(r.erro){ toast(r.erro,true); return; }
  if(nome==="ml-login") toast("Abrindo o Chrome… faça login e feche o navegador.");
  else if(nome==="instalar-navegador") toast("Baixando (~120 MB), acompanhe a saída.");
}

async function toggleBot(){
  const rota = statusAtual.bot_rodando ? "/api/stop" : "/api/start";
  await fetch(rota,{method:"POST"}); atualizar();
}

async function atualizar(){
  statusAtual = await (await fetch("/api/status")).json();
  const on = statusAtual.bot_rodando;
  $("#dot").className = "dot" + (on?" on":"");
  $("#btnAuto").textContent = statusAtual.autostart ? "✅ Ligado com o Windows — clique para desativar" : "⚡ Iniciar junto com o Windows";
  $("#btnAutoAgora").classList.toggle("hide", !statusAtual.autostart || on);
  $("#stt").textContent = on ? (statusAtual.bot_em_segundo_plano ? "Bot rodando (segundo plano)" : "Bot rodando") : (statusAtual.pronto ? "Pronto para ligar" : "Falta configurar");
  const b = $("#btnBot"); b.textContent = on ? "Desligar bot" : "Ligar bot";
  b.className = on ? "stop" : "pri";
  b.disabled = !on && !statusAtual.pronto;
  $("#a_nav").textContent = statusAtual.navegador ? "✓ Navegador instalado" : "⬇️ Instalar navegador";
  $("#a_ml").textContent = statusAtual.sessao_ml ? "✓ Login ML feito (refazer)" : "🔑 Login Mercado Livre";
}

async function puxarLogs(){
  const [lb, la] = await Promise.all([
    fetch("/api/logs?bot").then(r=>r.json()),
    fetch("/api/logs?acao").then(r=>r.json()),
  ]);
  if(lb.linhas.length){ const e=$("#logBot"); const b=e.scrollTop+e.clientHeight>=e.scrollHeight-30;
    e.textContent = lb.linhas.join("\n"); if(b) e.scrollTop = e.scrollHeight; }
  if(la.linhas.length){ const e=$("#logAcao"); const b=e.scrollTop+e.clientHeight>=e.scrollHeight-30;
    e.textContent = la.linhas.join("\n"); if(b) e.scrollTop = e.scrollHeight; }
}

// ── Canais ─────────────────────────────────────────────────────────
let CANAIS = [], CATALOGO = [], EDITANDO = -1, NICHOS_SEL = new Set();

async function carregarCanais(){
  const r = await (await fetch("/api/canais")).json();
  CANAIS = r.canais || []; CATALOGO = r.catalogo || [];
  desenharCanais();
}

function nomeNicho(k){ const n = CATALOGO.find(x=>x.chave===k); return n ? `${n.emoji} ${n.nome}` : k; }

function desenharCanais(){
  if(!CANAIS.length){
    $("#listaCanais").innerHTML = `<p class="muted">Nenhum canal ainda. Clique em <b>➕ Novo canal</b> para criar o primeiro.</p>`;
    return;
  }
  $("#listaCanais").innerHTML = CANAIS.map((c,i)=>{
    const badges = c.nichos.map(k=>`<span class="badge">${esc(nomeNicho(k))}</span>`).join("")
      + (c.palavras.length ? `<span class="badge">🔤 ${c.palavras.length} palavra(s)-chave</span>` : "")
      + (c.ml_etiqueta || c.amazon_tag ? `<span class="badge">📈 medido em separado</span>` : "")
      + (!c.nichos.length && !c.palavras.length ? `<span class="badge">⚠️ sem filtro: posta de tudo</span>` : "");
    return `<div class="canal ${c.ativo?'':'off'}">
      <span class="emo">${esc(c.emoji)}</span>
      <div class="info"><div class="nm">${esc(c.nome)} ${c.ativo?'':'<span class="muted">(pausado)</span>'}</div>
        <div class="sub">${esc(c.chat_id)}</div><div>${badges}</div></div>
      <div class="acoes">
        <button onclick="testarCanal(${i})">📨 Testar</button>
        <button onclick="editarCanal(${i})">✏️ Editar</button>
        <button onclick="alternarCanal(${i})">${c.ativo?'⏸ Pausar':'▶️ Ativar'}</button>
        <button onclick="excluirCanal(${i})">🗑</button>
      </div></div>`;
  }).join("");
}

function desenharNichos(){
  $("#nichosGrid").innerHTML = CATALOGO.map(n =>
    `<div class="nicho${NICHOS_SEL.has(n.chave)?' on':''}" data-k="${n.chave}" onclick="toggleNicho('${n.chave}')">
       <span class="emo">${n.emoji}</span><span class="nm">${esc(n.nome)}</span><span class="ck">✓</span>
     </div>`).join("");
}
function toggleNicho(k){
  if(NICHOS_SEL.has(k)) NICHOS_SEL.delete(k); else NICHOS_SEL.add(k);
  document.querySelector(`.nicho[data-k="${k}"]`).classList.toggle("on");
}

function abrirForm(c, idx){
  EDITANDO = idx;
  $("#fcTitulo").textContent = idx<0 ? "Novo canal" : "Editar canal";
  $("#c_emoji").value = c.emoji; $("#c_nome").value = c.nome; $("#c_chat").value = c.chat_id;
  $("#c_palavras").value = c.palavras.join(", "); $("#c_excluir").value = c.excluir.join(", ");
  $("#c_desc").value = c.desconto_minimo ?? ""; $("#c_max").value = c.max_posts_por_ciclo ?? "";
  $("#c_mletq").value = c.ml_etiqueta || ""; $("#c_amztag").value = c.amazon_tag || "";
  NICHOS_SEL = new Set(c.nichos); desenharNichos();
  $("#idsBoxCanal").classList.add("hide");
  $("#formCanal").classList.remove("hide");
  $("#formCanal").scrollIntoView({behavior:"smooth", block:"center"});
}
function novoCanal(){
  abrirForm({emoji:"📢",nome:"",chat_id:"",nichos:[],palavras:[],excluir:[],desconto_minimo:null,max_posts_por_ciclo:null,ativo:true}, -1);
}
function editarCanal(i){ abrirForm(CANAIS[i], i); }
function fecharForm(){ $("#formCanal").classList.add("hide"); EDITANDO = -1; }

async function gravarCanais(msg){
  const r = await (await fetch("/api/canais",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({canais:CANAIS})})).json();
  if(r.erro){ toast(r.erro,true); return false; }
  toast(msg);
  if(statusAtual.bot_rodando) $("#btnReiniciar").classList.remove("hide");
  await carregarCanais(); atualizar();
  return true;
}

async function salvarCanal(){
  const lista = t => t.split(/[,\n]/).map(x=>x.trim()).filter(Boolean);
  const num = v => v===""? null : parseInt(v,10);
  const antigo = EDITANDO>=0 ? CANAIS[EDITANDO] : null;
  const c = {
    id: antigo ? antigo.id : "", ativo: antigo ? antigo.ativo : true,
    emoji: $("#c_emoji").value.trim() || "📢", nome: $("#c_nome").value.trim(), chat_id: $("#c_chat").value.trim(),
    nichos: [...NICHOS_SEL], palavras: lista($("#c_palavras").value), excluir: lista($("#c_excluir").value),
    desconto_minimo: num($("#c_desc").value), max_posts_por_ciclo: num($("#c_max").value),
    ml_etiqueta: $("#c_mletq").value.trim(), amazon_tag: $("#c_amztag").value.trim(),
  };
  if(!c.nome || !c.chat_id){ toast("Preencha o nome e o ID do canal.", true); return; }
  if(!c.nichos.length && !c.palavras.length &&
     !confirm("Este canal está sem nicho e sem palavras-chave: vai postar ofertas de TUDO. Continuar?")) return;
  const copia = CANAIS.slice();
  if(EDITANDO>=0) CANAIS[EDITANDO] = c; else CANAIS.push(c);
  if(await gravarCanais("Canal salvo!")) fecharForm(); else CANAIS = copia;
}

async function alternarCanal(i){ CANAIS[i].ativo = !CANAIS[i].ativo; await gravarCanais(CANAIS[i].ativo ? "Canal ativado." : "Canal pausado."); }
async function excluirCanal(i){
  if(!confirm(`Excluir o canal "${CANAIS[i].nome}"? (O canal no Telegram não é afetado; só o bot deixa de postar nele.)`)) return;
  CANAIS.splice(i,1); await gravarCanais("Canal excluído.");
}
async function testarCanal(i){
  const r = await (await fetch("/api/canal-teste",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({chat_id:CANAIS[i].chat_id, nome:CANAIS[i].nome})})).json();
  if(r.ok) toast("Mensagem de teste enviada — confira o canal."); else toast(r.erro || "Falhou.", true);
}
async function reiniciarBot(){
  $("#btnReiniciar").classList.add("hide");
  await fetch("/api/stop",{method:"POST"}); await new Promise(r=>setTimeout(r,1500));
  await fetch("/api/start",{method:"POST"}); toast("Bot reiniciado com os canais novos."); atualizar();
}

async function alternarAuto(){
  const acao = statusAtual.autostart ? "remover" : "instalar";
  const r = await (await fetch("/api/autostart",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({acao})})).json();
  if(!r.ok){ toast(r.erro || "Não consegui alterar.", true); return; }
  toast(acao==="instalar" ? "Ativado! O bot vai iniciar sozinho quando você entrar no Windows." : "Início automático desativado.");
  atualizar();
}
async function iniciarAgora(){
  const r = await (await fetch("/api/autostart",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({acao:"iniciar"})})).json();
  toast(r.ok ? "Iniciando em segundo plano… aguarde alguns segundos." : (r.erro || "Falhou."), !r.ok);
  setTimeout(atualizar, 4000);
}

let toastT;
function toast(msg,err){ const t=$("#toast"); t.textContent=msg; t.className="toast show"+(err?" err":"");
  clearTimeout(toastT); toastT=setTimeout(()=>t.className="toast"+(err?" err":""),3200); }

carregarCfg(); carregarCanais(); atualizar(); puxarLogs();
setInterval(atualizar, 2500);
setInterval(puxarLogs, 1500);
</script>
</body>
</html>
"""
