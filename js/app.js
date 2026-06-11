import { prever, analisarOdds, CFG } from './elo.js';

const $ = s => document.querySelector(s);
const dados = {};            // {atp: {...}, wta: {...}}
let indice = [];             // [{n, tour, ref}]

async function carregar() {
  const [atp, wta, modAtp, modWta, taAtp, taWta, poly] = await Promise.all([
    fetch('data/atp.json').then(r => r.json()),
    fetch('data/wta.json').then(r => r.json()),
    fetch('data/modelos_atp.json').then(r => r.json()).catch(() => null),
    fetch('data/modelos_wta.json').then(r => r.json()).catch(() => null),
    fetch('data/ta_atp.json').then(r => r.json()).catch(() => null),
    fetch('data/ta_wta.json').then(r => r.json()).catch(() => null),
    fetch('data/polymarket.json').then(r => r.json()).catch(() => null),
  ]);
  dados.atp = atp; dados.wta = wta;
  dados.modelos = { atp: modAtp, wta: modWta };
  dados.ta = { atp: taAtp, wta: taWta };
  dados.poly = poly;
  for (const tour of ['atp', 'wta'])
    for (const j of dados[tour].jogadores) indice.push({ n: j.n, tour, ref: j });
  const dl = $('#listaJogadores');
  dl.innerHTML = indice.map(x => `<option value="${x.n}">`).join('');
  document.querySelectorAll('.dataCorte').forEach(e => e.textContent = atp.data_corte);
  montarRanking('atp');
}

function norm(s) {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
}

function achar(nome) {
  if (!nome) return null;
  const q = norm(nome);
  let cands = indice.filter(x => norm(x.n) === q);
  if (!cands.length) cands = indice.filter(x => norm(x.n).includes(q));
  if (!cands.length) {
    const sobren = q.split(' ').pop();
    cands = indice.filter(x => norm(x.n).split(' ').pop() === sobren);
  }
  cands.sort((a, b) => (b.ref.u || '').localeCompare(a.ref.u || '') || b.ref.m - a.ref.m);
  return cands[0] || null;
}

// ---------- abas ----------
document.querySelectorAll('.aba').forEach(b => b.addEventListener('click', () => {
  document.querySelectorAll('.aba').forEach(x => x.classList.remove('ativa'));
  document.querySelectorAll('.painel').forEach(x => x.classList.remove('ativa'));
  b.classList.add('ativa');
  $('#' + b.dataset.aba).classList.add('ativa');
  window.scrollTo({ top: 0 });
}));

// chips genéricos
function chipValor(id) { return $(id).querySelector('.ativa').dataset.v; }
document.querySelectorAll('.chips').forEach(g => g.addEventListener('click', e => {
  const c = e.target.closest('.chip'); if (!c) return;
  g.querySelectorAll('.chip').forEach(x => x.classList.remove('ativa'));
  c.classList.add('ativa');
  if (g.id === 'chipsTour' || g.id === 'chipsModelo') montarRanking(chipValor('#chipsTour'));
}));

// ---------- previsão ----------
$('#btnPrever').addEventListener('click', () => {
  const A = achar($('#jogadorA').value);
  const B = achar($('#jogadorB').value);
  const alvo = $('#resultado');
  alvo.classList.remove('oculto');
  if (!A || !B) {
    alvo.innerHTML = `<div class="res-cartao">Não encontrei ${!A ? `<strong>${$('#jogadorA').value || 'o jogador A'}</strong>` : `<strong>${$('#jogadorB').value || 'o jogador B'}</strong>`} entre os ${indice.length} jogadores ativos (≥30 partidas, em atividade no último ano). Tente o sobrenome.</div>`;
    return;
  }
  if (A.tour !== B.tour) {
    alvo.innerHTML = `<div class="res-cartao">${A.n} (${A.tour.toUpperCase()}) e ${B.n} (${B.tour.toUpperCase()}) jogam em circuitos diferentes.</div>`;
    return;
  }
  const piso = chipValor('#chipsPiso');
  const bo = +chipValor('#chipsBo');
  const altitude = chipValor('#chipsAlt') === '1';
  const { p, ra, rb } = prever(A.ref, B.ref, { piso, bo, altitude });
  const pisoNome = { H: 'duro', C: 'saibro', G: 'grama' }[piso];

  const meta = j => `Elo ${Math.round(j.ref.e)} · ${pisoNome} ${j.ref.s[piso] ? Math.round(j.ref.s[piso]) : '—'} · ${j.ref.m} jogos${j.ref.r ? ' · #' + j.ref.r : ''}`;
  let html = `
  <div class="res-cartao">
    <div class="res-nomes">
      <span>${A.n}<br><span class="jog-meta">${meta(A)}</span></span>
      <span style="text-align:right">${B.n}<br><span class="jog-meta">${meta(B)}</span></span>
    </div>
    <div class="barra"><div style="width:${(p * 100).toFixed(1)}%"></div></div>
    <div class="res-prob"><span>${(p * 100).toFixed(1)}%</span><span>${((1 - p) * 100).toFixed(1)}%</span></div>
    <div class="linha-info">
      <span>Odd justa: <span class="mono">${(1 / p).toFixed(2)}</span></span>
      <span>${A.tour.toUpperCase()} · ${pisoNome} · melhor de ${bo}${altitude ? ' · altitude' : ''} · rating confronto <span class="mono">${Math.round(ra)} vs ${Math.round(rb)}</span></span>
      <span>Odd justa: <span class="mono">${(1 / (1 - p)).toFixed(2)}</span></span>
    </div>
  </div>`;

  const oa = parseFloat($('#oddA').value), ob = parseFloat($('#oddB').value);
  if (oa > 1 && ob > 1) {
    const casa = $('#casaNome').value;
    const banca = parseFloat($('#banca').value) || 1000;
    const an = analisarOdds(p, oa, ob, banca);
    const lado = (l, nome) => `
      <div class="ev-lado${l.valor ? ' valor' : ''}">
        <div style="font-weight:600">${nome} <span class="mono" style="color:var(--texto-2)">@${l.o.toFixed(2)}</span></div>
        <div class="ev-num ${l.ev >= 0 ? 'ev-pos' : 'ev-neg'}">EV ${(l.ev * 100).toFixed(1)}%</div>
        <div class="jog-meta">mercado sem vig: ${(l.q * 100).toFixed(1)}% · Kelly ¼: R$ ${l.stake.toFixed(0)}</div>
        ${l.valor ? '<span class="selo-valor">✅ valor nominal</span>' : ''}
      </div>`;
    html += `
    <div class="res-cartao">
      <div class="res-nomes"><span>vs ${casa} (vig ${(an.vig * 100).toFixed(1)}%)</span><span class="jog-meta">remoção de vig: método power</span></div>
      <div class="ev-grid">${lado(an.lados[0], A.n)}${lado(an.lados[1], B.n)}</div>
      ${an.antiSinal ? `<div class="alerta-anti"><strong>⚠ Anti-sinal:</strong> o modelo discorda ${(an.desacordo * 100).toFixed(0)} p.p. do mercado. No backtest, desacordo grande contra linha de FECHAMENTO deu ROI de −9% a −19% — o mercado costuma saber algo (lesão, notícia, forma). Só considere se esta odd é de abertura ou promoção.</div>` : ''}
      ${!an.lados.some(l => l.valor) && !an.antiSinal ? `<p class="aviso-leve">Sem valor: nenhum lado passa dos filtros (EV ≥ ${CFG.evMinimo * 100}%, prob. implícita ≥ ${CFG.qMinimo * 100}%, teto ${CFG.evTeto * 100}%).</p>` : ''}
      <p class="aviso-leve">Estudo estatístico, não recomendação. Contra closing line o backtest deu ROI −5,5% — valor real só em linhas de abertura/soft books.</p>
    </div>`;
  }
  // ---- outros modelos no mesmo confronto ----
  const mods = dados.modelos[A.tour];
  if (mods) {
    const linhas = [];
    const esc480 = (p * 100).toFixed(1);
    linhas.push(`<tr><td><strong>Jony Greens v1.1</strong> <span class="jog-meta">calibrado</span></td><td class="num">${esc480}%</td><td class="num">${(1 / p).toFixed(2)}</td></tr>`);
    for (const [chave, m] of Object.entries(mods.modelos)) {
      if (chave === 'nosso') continue;
      const ja = m.jogadores.find(j => norm(j.n) === norm(A.n));
      const jb = m.jogadores.find(j => norm(j.n) === norm(B.n));
      if (!ja || !jb) continue;
      const w = m.blend, esc = m.escala;
      const rA = w * ja.e + (1 - w) * (ja.s && ja.s[piso] != null ? ja.s[piso] : ja.e);
      const rB = w * jb.e + (1 - w) * (jb.s && jb.s[piso] != null ? jb.s[piso] : jb.e);
      const pm = 1 / (1 + Math.pow(10, (rB - rA) / esc));
      linhas.push(`<tr><td>${m.rotulo}</td><td class="num">${(pm * 100).toFixed(1)}%</td><td class="num">${(1 / pm).toFixed(2)}</td></tr>`);
    }
    const ta = dados.ta[A.tour];
    if (ta) {
      const ja = ta.jogadores.find(j => norm(j.n) === norm(A.n));
      const jb = ta.jogadores.find(j => norm(j.n) === norm(B.n));
      if (ja && jb) {
        const rA = 0.5 * ja.e + 0.5 * (ja.s && ja.s[piso] != null ? ja.s[piso] : ja.e);
        const rB = 0.5 * jb.e + 0.5 * (jb.s && jb.s[piso] != null ? jb.s[piso] : jb.e);
        const pt = 1 / (1 + Math.pow(10, (rB - rA) / 400));
        linhas.push(`<tr><td>Tennis Abstract <span class="jog-meta">snapshot ${ta.atualizado}</span></td><td class="num">${(pt * 100).toFixed(1)}%</td><td class="num">${(1 / pt).toFixed(2)}</td></tr>`);
      }
    }
    if (linhas.length > 1) {
      html += `<div class="res-cartao"><div class="res-nomes"><span>O que cada modelo diz (${A.n})</span><span class="jog-meta">reimplementações sempre atualizadas nos mesmos dados</span></div>
      <table><thead><tr><th>Modelo</th><th>p(${A.n.split(' ').pop()})</th><th>odd justa</th></tr></thead><tbody>${linhas.join('')}</tbody></table>
      <p class="aviso-leve">Leque apertado = consenso entre métodos; leque aberto = confronto incerto (novato, volta de lesão, piso raro). Só o nosso é calibrado (escala 480) e validado em holdout.</p></div>`;
    }
  }

  // ---- Polymarket (snapshot do bot, 8/8h) ----
  if (dados.poly && dados.poly.mercados) {
    const sa = norm(A.n).split(' ').pop(), sb = norm(B.n).split(' ').pop();
    const mk = dados.poly.mercados.find(x => { const t = norm(x.t); return t.includes(sa) && t.includes(sb); });
    if (mk) {
      const idxA = norm(mk.lados[0] || '').includes(sa) ? 0 : 1;
      const prA = mk.precos[idxA], prB = mk.precos[1 - idxA];
      if (prA > 0 && prB > 0) {
        const evA = p * (1 / prA) - 1, evB = (1 - p) * (1 / prB) - 1;
        html += `<div class="res-cartao"><div class="res-nomes"><span>Polymarket (exchange, sem vig)</span><span class="jog-meta">snapshot ${dados.poly.capturado_em.slice(0, 16).replace('T', ' ')} UTC · vol US$ ${mk.volume.toLocaleString()}</span></div>
        <div class="ev-grid">
          <div class="ev-lado${evA >= CFG.evMinimo && evA <= CFG.evTeto && prA >= CFG.qMinimo ? ' valor' : ''}"><div style="font-weight:600">${A.n} <span class="mono" style="color:var(--texto-2)">@${(1 / prA).toFixed(2)}</span></div><div class="ev-num ${evA >= 0 ? 'ev-pos' : 'ev-neg'}">EV ${(evA * 100).toFixed(1)}%</div><div class="jog-meta">preço ${prA.toFixed(2)} = ${(prA * 100).toFixed(0)}%</div></div>
          <div class="ev-lado${evB >= CFG.evMinimo && evB <= CFG.evTeto && prB >= CFG.qMinimo ? ' valor' : ''}"><div style="font-weight:600">${B.n} <span class="mono" style="color:var(--texto-2)">@${(1 / prB).toFixed(2)}</span></div><div class="ev-num ${evB >= 0 ? 'ev-pos' : 'ev-neg'}">EV ${(evB * 100).toFixed(1)}%</div><div class="jog-meta">preço ${prB.toFixed(2)} = ${(prB * 100).toFixed(0)}%</div></div>
        </div>
        <p class="aviso-leve">Preços podem estar defasados (snapshot) e mercados de baixa liquidez distorcem. Confira o preço ao vivo antes de qualquer decisão.</p></div>`;
      }
    }
  }
  alvo.innerHTML = html;
});

// ---------- ranking ----------
function listaDoModelo(tour, modelo) {
  if (modelo === 'ta') {
    const ta = dados.ta[tour];
    return ta ? ta.jogadores.map(j => ({ ...j, m: '', r: null })) : [];
  }
  if (modelo !== 'nosso' && dados.modelos[tour])
    return dados.modelos[tour].modelos[modelo].jogadores;
  return dados[tour].jogadores;
}

function montarRanking(tour) {
  const modelo = document.querySelector('#chipsModelo') ? chipValor('#chipsModelo') : 'nosso';
  const t = $('#tabelaRanking');
  const fonteNota = $('#notaModelo');
  if (fonteNota) fonteNota.textContent = modelo === 'ta'
    ? 'Snapshot do Tennis Abstract (Jeff Sackmann), atualizado ' + (dados.ta[tour] ? dados.ta[tour].atualizado : '—') + ' — escala própria dele, não comparável ponto a ponto com a nossa.'
    : modelo === 'nosso' ? 'Nosso modelo v1.1 (calibrado, validado em holdout).'
    : dados.modelos[tour].modelos[modelo].rotulo + ' — reimplementação da fórmula rodada nos mesmos dados, sempre atualizada.';
  const linhas = listaDoModelo(tour, modelo).slice(0, 25).map((j, i) => `
    <tr>
      <td class="num ${i < 3 ? 'pos-top' : ''}">${i + 1}</td>
      <td><strong>${j.n}</strong>${j.r ? ` <span class="jog-meta">#${j.r} oficial</span>` : ''}</td>
      <td class="num">${Math.round(j.e)}</td>
      <td class="num">${j.s.H ? Math.round(j.s.H) : '—'}</td>
      <td class="num">${j.s.C ? Math.round(j.s.C) : '—'}</td>
      <td class="num">${j.s.G ? Math.round(j.s.G) : '—'}</td>
      <td class="num">${j.m}</td>
    </tr>`).join('');
  t.innerHTML = `<thead><tr><th>#</th><th>Jogador(a)</th><th>Elo</th><th>Duro</th><th>Saibro</th><th>Grama</th><th>Jogos</th></tr></thead><tbody>${linhas}</tbody>`;
}

carregar();
