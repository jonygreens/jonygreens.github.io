// Núcleo do modelo — port fiel de src/elo_core.py do tennis-elo-lab.
// Toda a matemática roda no navegador; os ratings vêm pré-computados (data/*.json).

export const CFG = {
  pesoBlendGeral: 0.5,    // R_confronto = 0.5*geral + 0.5*piso (Tennis Abstract, backtest 50k partidas)
  escalaProb: 480,        // calibração: corrige superconfiança do /400 (promovida: ΔLL≥0.002 nos 2 tours)
  escalaAltitude: 800,    // Bogotá/Guadalajara/Gstaad/Kitzbühel: gaps valem menos no ar rarefeito
  evMinimo: 0.05,
  qMinimo: 0.30,          // piso de prob. implícita devigada (corta cauda do favourite-longshot bias)
  evTeto: 0.25,           // EV acima disso = presumir erro de dados, não apostar
  fracaoKelly: 0.25,
  antiSinalLimiar: 0.05,  // desacordo ≥5pp com o mercado historicamente é ANTI-sinal
};

export function expected(ra, rb, escala = CFG.escalaProb) {
  return 1 / (1 + Math.pow(10, (rb - ra) / escala));
}

// best-of-5 assumindo sets iid: p_bo3 = s²(3−2s) → inverte por bissecção → p_bo5
function pBo3DeSet(s) { return s * s * (3 - 2 * s); }
function pBo5DeSet(s) { return s ** 3 * (10 - 15 * s + 6 * s * s); }
export function bo5Adjust(p) {
  if (p <= 0 || p >= 1) return p;
  let lo = 0, hi = 1;
  for (let i = 0; i < 50; i++) {
    const mid = (lo + hi) / 2;
    if (pBo3DeSet(mid) < p) lo = mid; else hi = mid;
  }
  return pBo5DeSet((lo + hi) / 2);
}

// remoção de vig pelo método POWER — único validado em tênis (Buchdahl, 68k partidas)
export function novigPower(oa, ob) {
  const q = [1 / oa, 1 / ob];
  let lo = 0.5, hi = 5;
  for (let i = 0; i < 80; i++) {
    const k = (lo + hi) / 2;
    if (Math.pow(q[0], k) + Math.pow(q[1], k) > 1) lo = k; else hi = k;
  }
  const k = (lo + hi) / 2;
  return [Math.pow(q[0], k), Math.pow(q[1], k)];
}

export function kellyCheio(p, o) {
  if (o <= 1) return 0;
  return Math.max((p * o - 1) / (o - 1), 0);
}

export function ratingConfronto(jog, piso) {
  const geral = jog.e;
  const doPiso = jog.s && jog.s[piso] != null ? jog.s[piso] : geral;
  return CFG.pesoBlendGeral * geral + (1 - CFG.pesoBlendGeral) * doPiso;
}

// previsão completa de um confronto
export function prever(jogA, jogB, { piso = 'H', bo = 3, altitude = false } = {}) {
  const ra = ratingConfronto(jogA, piso);
  const rb = ratingConfronto(jogB, piso);
  const escala = altitude ? CFG.escalaAltitude : CFG.escalaProb;
  let p = expected(ra, rb, escala);
  if (bo === 5) p = bo5Adjust(p);
  return { p, ra, rb };
}

// análise de valor contra odds de uma casa
export function analisarOdds(p, oa, ob, banca = 1000) {
  const [qa, qb] = novigPower(oa, ob);
  const vig = (1 / oa + 1 / ob - 1);
  const lados = [
    { rotulo: 'A', p, o: oa, q: qa },
    { rotulo: 'B', p: 1 - p, o: ob, q: qb },
  ].map(l => {
    const ev = l.p * l.o - 1;
    const kelly = kellyCheio(l.p, l.o) * CFG.fracaoKelly;
    return {
      ...l, ev,
      stake: Math.min(kelly, 0.02) * banca,            // cap duro de 2% da banca
      valor: ev >= CFG.evMinimo && ev <= CFG.evTeto && l.q >= CFG.qMinimo,
    };
  });
  const desacordo = Math.max(Math.abs(p - qa), Math.abs((1 - p) - qb));
  return { lados, vig, qa, qb, desacordo, antiSinal: desacordo >= CFG.antiSinalLimiar };
}
