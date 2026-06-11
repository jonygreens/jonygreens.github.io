# -*- coding: utf-8 -*-
"""
Nucleo do sistema de Elo de tenis (ATP/WTA).
Python puro (stdlib). Parametros 100% dirigidos por config (config.json).

Convencoes:
- Ratings: dict player_id -> float (geral) e (player_id, superficie) -> float.
- K dinamico: K = k_base / (n_partidas + k_offset)^k_shape, x multiplicador de nivel,
  x boost de retorno de inatividade.
- Predicao: blend de ratings r_blend = w*geral + (1-w)*superficie, prob logistica base 10/400.
- Toda probabilidade registrada para avaliacao e PRE-jogo (sem leakage).
"""
import csv
import math
import os
from datetime import date as _date

# Ordem de rounds para ordenacao cronologica intra-torneio (tourney_date e a data de INICIO do torneio)
ROUND_ORDER = {
    'Q1': 0, 'Q2': 1, 'Q3': 2, 'Q4': 3, 'ER': 4, 'RR': 5,
    'R128': 6, 'R64': 7, 'R32': 8, 'R16': 9, 'QF': 10, 'SF': 11, 'BR': 12, 'F': 13,
}

# Indices do registro de partida (tupla, por velocidade)
# ACT_ONLY: partida que so conta como atividade (RET excluido do treino, mas o relogio
# de inatividade nao pode disparar para quem esteve em quadra). MAIN: arquivo principal
# do tour (main draw) — universo da metrica primaria. FGAMES: fracao de games do
# vencedor (p/ MOV estilo WElo, EJOR 2022).
(SORT, ODATE, YEAR, SURF, LEVEL, BO, WID, LID, WNAME, LNAME, WRANK, LRANK,
 ACT_ONLY, MAIN, FGAMES, WSETS, LSETS) = range(17)

# Niveis de quals de tour presentes nos arquivos qual/itf
_TOUR_LEVELS = ('G', 'M', 'A', 'F', 'D', 'PM', 'P', 'I')

SURFACES = ('Hard', 'Clay', 'Grass', 'Carpet')


def placar_resumo(score):
    """(fracao de games do vencedor, sets do vencedor, sets do perdedor) a partir do
    placar Sackmann ('6-3 7-6(4)'). Ignora detalhe de tie-break; super-TB conta como
    set 1-0. Placar imprestavel -> (0.5, 1, 0)."""
    gw = gl = sw = sl = 0
    for tok in score.replace('[', ' ').replace(']', ' ').split():
        base = tok.split('(')[0]
        parts = base.split('-')
        if len(parts) != 2:
            continue
        try:
            a, b = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        if a > 20 or b > 20:  # super tie-break: 1 game pro vencedor do set
            a, b = (1, 0) if a > b else (0, 1)
        gw += a
        gl += b
        if a > b:
            sw += 1
        elif b > a:
            sl += 1
    tot = gw + gl
    return (gw / tot if tot > 0 else 0.5, sw if (sw or sl) else 1, sl)


def games_share(score):
    return placar_resumo(score)[0]


def parse_yyyymmdd(s):
    y, m, d = int(s[:4]), int(s[4:6]), int(s[6:8])
    return _date(y, m, d)


def _to_int(x):
    try:
        return int(float(x))
    except (TypeError, ValueError):
        return None


def load_matches(repo_dir, prefix, year_from, year_to, include_qual_chall=False,
                 include_futures=False, carpet_as='Hard', count_walkovers=False,
                 count_retirements=True):
    """Le os CSVs do Sackmann e devolve lista de partidas ordenada cronologicamente."""
    rows = []
    for y in range(year_from, year_to + 1):
        files = [('%s_matches_%d.csv' % (prefix, y), True, False)]
        if include_qual_chall:
            if prefix == 'atp':
                files.append(('%s_matches_qual_chall_%d.csv' % (prefix, y), False, False))
            else:  # WTA: quals de tour + ITF >= 50k + WTA 125 ('C')
                files.append(('%s_matches_qual_itf_%d.csv' % (prefix, y), False, True))
        if include_futures:
            files.append(('%s_matches_futures_%d.csv' % (prefix, y), False, False))
        for fn, is_main, filtra_itf in files:
            path = os.path.join(repo_dir, fn)
            if not os.path.exists(path):
                continue
            with open(path, newline='', encoding='utf-8') as f:
                for r in csv.DictReader(f):
                    level = (r.get('tourney_level') or '').strip()
                    if filtra_itf and level not in _TOUR_LEVELS and level != 'C':
                        try:
                            if int(level) < 50:
                                continue
                        except ValueError:
                            continue
                    score = (r.get('score') or '').strip().upper()
                    # Partidas nao disputadas / abandonadas nao movem rating
                    if ('W/O' in score and not count_walkovers) or 'DEF' in score \
                            or 'ABN' in score or 'ABD' in score or 'WEA' in score \
                            or score in ('', 'UNK', 'NA', '(W/O)'):
                        continue
                    # RET fora do treino, mas conta como atividade (jogador esteve em quadra)
                    act_only = 'RET' in score and not count_retirements
                    try:
                        od = parse_yyyymmdd(r['tourney_date'].strip()).toordinal()
                        wid = int(r['winner_id'])
                        lid = int(r['loser_id'])
                    except (KeyError, ValueError, TypeError):
                        continue
                    if wid == lid:
                        continue
                    surface = (r.get('surface') or '').strip().title()
                    if surface == 'Carpet':
                        # 'geral_apenas': sem rating de superficie (so Elo geral);
                        # 'Carpet': 4a superficie propria; 'Hard': funde com duro
                        surface = None if carpet_as == 'geral_apenas' else carpet_as
                    if surface not in SURFACES:
                        surface = None
                    try:
                        bo = int(r.get('best_of') or 3)
                    except (ValueError, TypeError):
                        bo = 3
                    try:
                        mn = int(r.get('match_num') or 0)
                    except (ValueError, TypeError):
                        mn = 0
                    ro = ROUND_ORDER.get((r.get('round') or '').strip(), 8)
                    rows.append((
                        (od, r.get('tourney_id') or '', ro, mn),
                        od, int(r['tourney_date'][:4]), surface, level, bo,
                        wid, lid,
                        (r.get('winner_name') or '').strip(),
                        (r.get('loser_name') or '').strip(),
                        _to_int(r.get('winner_rank')), _to_int(r.get('loser_rank')),
                        act_only, is_main,
                    ) + placar_resumo(score))
    rows.sort(key=lambda t: t[0])
    return rows


def expected(ra, rb, escala=400.0):
    """Probabilidade de A vencer B (curva logistica base 10).

    escala > 400 encolhe probabilidades rumo a 50% — recalibracao de 1 parametro
    para corrigir superconfianca SEM mexer na dinamica de atualizacao (que fica em 400).
    """
    return 1.0 / (1.0 + 10.0 ** ((rb - ra) / escala))


def k_factor(n, cfg, rating=None):
    """K dinamico. Default: potencia 538 (experiencia). Alternativa 'uts': kFunction do
    Ultimate Tennis Statistics — K depende do NIVEL DE RATING, nao da experiencia."""
    if cfg.get('k_modelo') == 'uts' and rating is not None:
        return 32.0 * (1.0 + 18.0 / (1.0 + 2.0 ** ((rating - 1500.0) / 63.0)))
    return cfg['k_base'] / ((n + cfg['k_offset']) ** cfg['k_shape'])


def level_mult(level, cfg):
    if level == 'G':
        return cfg['mult_k_slam']
    if level in ('M', 'PM', 'F'):  # Masters / WTA 1000 / Finals
        return cfg['mult_k_masters']
    if level == 'D':  # Davis Cup / BJK Cup
        return cfg['mult_k_davis']
    return 1.0


# ---------- Transformacao best-of-5 (sets iid) ----------

def p_bo3_from_set(s):
    return s * s * (3.0 - 2.0 * s)


def p_bo5_from_set(s):
    return s ** 3 * (10.0 - 15.0 * s + 6.0 * s * s)


def set_prob_from_bo3(p):
    """Inverte p = s^2(3-2s) por bissecao (monotonica em [0,1])."""
    lo, hi = 0.0, 1.0
    for _ in range(50):
        mid = (lo + hi) / 2.0
        if p_bo3_from_set(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def bo5_adjust(p):
    """Converte prob calibrada em bo3 para bo5 assumindo sets iid."""
    if p <= 0.0 or p >= 1.0:
        return p
    return p_bo5_from_set(set_prob_from_bo3(p))


# ---------- Motor principal ----------

# Tabela cold-start do Ultimate Tennis Statistics: rank oficial -> Elo de entrada
_RANK_ELO = [(1, 2405), (2, 2336), (3, 2285), (4, 2246), (5, 2213), (7, 2178),
             (10, 2140), (15, 2097), (20, 2058), (30, 2011), (50, 1947), (70, 1889),
             (100, 1836), (150, 1776), (200, 1714), (1000, 1500)]


def entry_por_rank(rank, default=1500.0):
    """Elo de entrada interpolado pelo ranking oficial no 1o jogo (UTS StartEloRatings)."""
    if rank is None or rank >= 1000:
        return default
    if rank <= 1:
        return float(_RANK_ELO[0][1])
    for (r0, e0), (r1, e1) in zip(_RANK_ELO, _RANK_ELO[1:]):
        if r0 <= rank <= r1:
            return e0 + (e1 - e0) * (rank - r0) / (r1 - r0)
    return default


def rd_aproximado(m_count):
    """Incerteza HEURISTICA do rating (estilo Glicko RD, mesma escala logistica 400).

    NAO e uma quantidade ajustada aos dados — e uma aproximacao documentada:
    350 (incerteza de novato no Glicko) decaindo com a raiz das partidas, piso 50.
    Uso: faixa indicativa de confianca no ranking, nunca entra na previsao.
    """
    return max(50.0, 350.0 / math.sqrt(1.0 + m_count / 20.0))


def run_elo(matches, cfg, eval_from_year=None, history=None):
    """
    Passa o Elo por todas as partidas em ordem cronologica.
    Devolve (state, evals). Probabilidades em evals sao PRE-jogo.
    history: lista opcional — recebe (ordinal, player_id, rating_pos_jogo) por update.
    """
    init = cfg['rating_inicial']
    w_blend = cfg['peso_blend_geral']
    surf_from_overall = cfg['iniciar_superficie_do_geral']
    inact_days = cfg.get('dias_inatividade') or 0
    pen = cfg.get('penalidade_retorno_pts') or 0.0
    kboost = cfg.get('boost_k_retorno') or 1.0
    nboost = cfg.get('partidas_boost_retorno') or 0
    use_bo5 = cfg.get('ajuste_bo5') == 'transformacao_sets_iid'
    incl_davis = cfg.get('incluir_davis', True)
    esc = cfg.get('escala_prob', 400.0)
    use_welo = cfg.get('mov') == 'welo_games'
    init_chall = cfg.get('rating_inicial_challenger') or init   # entrada dual (TA: low 1200s)
    entrada_rank = cfg.get('entrada_por_rank', False)           # cold start UTS: Elo do rank oficial
    w_surf_map = cfg.get('peso_blend_superficies') or {}        # blend por superficie
    grama_hard = cfg.get('grama_ancora_hard', False)            # grama blendada com duro
    lam = cfg.get('regressao_anual') or 0.0                     # shrink sazonal (538 NFL)
    season = {}
    theta = cfg.get('set_elo_peso') or 0.0                      # set-Elo paralelo (UTS)
    rset = {}

    r = {}          # id -> elo geral
    rs = {}         # (id, surf) -> elo superficie
    n = {}          # id -> partidas (geral)
    ns = {}         # (id, surf) -> partidas na superficie
    last = {}       # id -> ordinal da ultima partida
    boost = {}      # id -> partidas restantes com K turbinado
    peak = {}       # id -> (pico, ordinal)
    names = {}      # id -> nome mais recente
    lastrank = {}   # id -> ultimo ranking oficial visto

    evals = []

    for m in matches:
        if m[LEVEL] == 'D' and not incl_davis:
            continue
        od = m[ODATE]
        wid, lid, surf = m[WID], m[LID], m[SURF]

        # RET fora do treino: so refresca o relogio de atividade e metadados
        if m[ACT_ONLY]:
            last[wid] = od
            last[lid] = od
            names[wid] = m[WNAME]
            names[lid] = m[LNAME]
            continue

        # --- retorno de inatividade (aplica ANTES de prever: ferrugem afeta este jogo) ---
        if inact_days > 0:
            for pid in (wid, lid):
                lp = last.get(pid)
                if lp is not None and (od - lp) >= inact_days:
                    if pen:
                        if pid in r:
                            r[pid] -= pen
                        for s in SURFACES:
                            k = (pid, s)
                            if k in rs:
                                rs[k] -= pen
                    if nboost:
                        boost[pid] = nboost

        # --- regressao sazonal (lazy, na 1a partida do jogador no ano) ---
        if lam:
            yr = m[YEAR]
            for pid in (wid, lid):
                if pid in r and season.get(pid, yr) != yr:
                    r[pid] = 1500.0 + (1.0 - lam) * (r[pid] - 1500.0)
                    for s in SURFACES:
                        k2 = (pid, s)
                        if k2 in rs:
                            rs[k2] = 1500.0 + (1.0 - lam) * (rs[k2] - 1500.0)
                season[pid] = yr

        # entrada dual: quem estreia em challenger/ITF/quali entra mais baixo
        ent = init
        if init_chall != init and (m[LEVEL] not in _TOUR_LEVELS or m[SORT][2] <= 3):
            ent = init_chall
        if entrada_rank:
            rw = r.get(wid) or entry_por_rank(m[WRANK], init)
            rl = r.get(lid) or entry_por_rank(m[LRANK], init)
        else:
            rw = r.get(wid, ent)
            rl = r.get(lid, ent)
        if surf is not None:
            kws, kls = (wid, surf), (lid, surf)
            rsw = rs.get(kws, rw if surf_from_overall else init)
            rsl = rs.get(kls, rl if surf_from_overall else init)
        else:
            rsw, rsl = rw, rl

        # --- probabilidades PRE-jogo (escala calibrada) ---
        p_o = expected(rw, rl, esc)
        p_s = expected(rsw, rsl, esc)
        w_m = w_surf_map.get(surf, w_blend) if surf is not None else w_blend
        if grama_hard and surf == 'Grass':
            anc_w = rs.get((wid, 'Hard'), rw)
            anc_l = rs.get((lid, 'Hard'), rl)
        else:
            anc_w, anc_l = rw, rl
        p_b = expected(w_m * anc_w + (1 - w_m) * rsw,
                       w_m * anc_l + (1 - w_m) * rsl, esc)
        if theta:
            stw = rset.get(wid, rw)
            stl = rset.get(lid, rl)
            p_b = (1 - theta) * p_b + theta * expected(stw, stl, esc)
        if use_bo5 and m[BO] == 5:
            p_b = bo5_adjust(p_b)

        if eval_from_year is not None and m[YEAR] >= eval_from_year:
            evals.append((m[YEAR], m[LEVEL], surf or '?', m[BO], p_b, p_o, p_s,
                          od, wid, lid, m[WRANK], m[LRANK], m[MAIN]))

        # --- atualizacao ---
        lm = level_mult(m[LEVEL], cfg)
        bw = kboost if boost.get(wid, 0) > 0 else 1.0
        bl = kboost if boost.get(lid, 0) > 0 else 1.0
        kw = k_factor(n.get(wid, 0), cfg, rw) * lm * bw
        kl = k_factor(n.get(lid, 0), cfg, rl) * lm * bl
        # MOV estilo WElo (EJOR 2022): update ponderado pela fracao de games do vencedor
        fg = m[FGAMES] if use_welo else None
        delta = 1.0 - (p_o if esc == 400.0 else expected(rw, rl))
        if fg is not None:
            delta *= fg
        r[wid] = rw + kw * delta
        r[lid] = rl - kl * delta

        if surf is not None:
            ksw = k_factor(ns.get(kws, 0), cfg, rsw) * lm * bw
            ksl = k_factor(ns.get(kls, 0), cfg, rsl) * lm * bl
            ds = 1.0 - (p_s if esc == 400.0 else expected(rsw, rsl))
            if fg is not None:
                ds *= fg
            rs[kws] = rsw + ksw * ds
            rs[kls] = rsl - ksl * ds
            ns[kws] = ns.get(kws, 0) + 1
            ns[kls] = ns.get(kls, 0) + 1

        # set-Elo (UTS): update do rating paralelo ponderado pelo placar de sets
        if theta:
            ps_upd = expected(rset.get(wid, rw), rset.get(lid, rl))
            base_w = rset.get(wid, rw)
            base_l = rset.get(lid, rl)
            rset[wid] = base_w + 0.5 * kw * ((1 - ps_upd) * m[WSETS] - ps_upd * m[LSETS])
            rset[lid] = base_l - 0.5 * kl * ((1 - ps_upd) * m[WSETS] - ps_upd * m[LSETS])

        n[wid] = n.get(wid, 0) + 1
        n[lid] = n.get(lid, 0) + 1
        last[wid] = od
        last[lid] = od
        if history is not None:
            history.append((od, wid, r[wid]))
            history.append((od, lid, r[lid]))
        if boost.get(wid, 0) > 0:
            boost[wid] -= 1
        if boost.get(lid, 0) > 0:
            boost[lid] -= 1
        if r[wid] > peak.get(wid, (-1e9, 0))[0]:
            peak[wid] = (r[wid], od)
        names[wid] = m[WNAME]
        names[lid] = m[LNAME]
        if m[WRANK] is not None:
            lastrank[wid] = m[WRANK]
        if m[LRANK] is not None:
            lastrank[lid] = m[LRANK]

    state = {'r': r, 'rs': rs, 'n': n, 'ns': ns, 'last': last, 'peak': peak,
             'names': names, 'lastrank': lastrank}
    return state, evals


# ---------- Metricas ----------

def metrics(evals, y0, y1, prob_idx=4):
    n = 0
    acc = 0.0
    ll = 0.0
    br = 0.0
    for e in evals:
        if e[0] < y0 or e[0] > y1:
            continue
        p = min(max(e[prob_idx], 1e-12), 1 - 1e-12)
        n += 1
        if p > 0.5:
            acc += 1
        elif p == 0.5:
            acc += 0.5
        ll += -math.log(p)
        br += (1.0 - p) ** 2
    if n == 0:
        return {'n': 0, 'acc': None, 'logloss': None, 'brier': None}
    return {'n': n, 'acc': acc / n, 'logloss': ll / n, 'brier': br / n}


def rank_baseline(evals, y0, y1):
    """Baseline: 'melhor ranking oficial vence'."""
    n = 0
    acc = 0.0
    for e in evals:
        if e[0] < y0 or e[0] > y1:
            continue
        wr, lr = e[10], e[11]
        if wr is None or lr is None:
            continue
        n += 1
        if wr < lr:
            acc += 1
        elif wr == lr:
            acc += 0.5
    return {'n': n, 'acc': (acc / n) if n else None}


def calibration(evals, y0, y1, prob_idx=4, n_buckets=10):
    """Calibracao pelo lado do favorito: p_fav em [0.5, 1.0]."""
    width = 0.5 / n_buckets
    buckets = [[0, 0.0, 0.0] for _ in range(n_buckets)]  # n, soma_p, acertos_fav
    for e in evals:
        if e[0] < y0 or e[0] > y1:
            continue
        p = e[prob_idx]
        fav_won = 1.0 if p >= 0.5 else 0.0
        pf = p if p >= 0.5 else 1.0 - p
        i = min(int((pf - 0.5) / width), n_buckets - 1)
        buckets[i][0] += 1
        buckets[i][1] += pf
        buckets[i][2] += fav_won
    out = []
    for i, (cnt, sp, hits) in enumerate(buckets):
        lo = 0.5 + i * width
        hi = lo + width
        out.append({'faixa': '%.2f-%.2f' % (lo, hi), 'n': cnt,
                    'previsto': (sp / cnt) if cnt else None,
                    'observado': (hits / cnt) if cnt else None})
    return out


# ---------- Remocao de vig e Kelly ----------

def novig_proporcional(odds):
    q = [1.0 / o for o in odds]
    s = sum(q)
    return [x / s for x in q]


def novig_power(odds):
    """Resolve k tal que sum((1/o_i)^k) = 1."""
    q = [1.0 / o for o in odds]
    lo, hi = 0.5, 5.0
    for _ in range(80):
        k = (lo + hi) / 2.0
        s = sum(x ** k for x in q)
        if s > 1.0:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2.0
    return [x ** k for x in q]


def novig_shin(odds):
    """Metodo de Shin (2 resultados): corrige favourite-longshot bias via insider trading z."""
    q = [1.0 / o for o in odds]
    Q = sum(q)

    def probs(z):
        return [(math.sqrt(z * z + 4.0 * (1.0 - z) * (x * x) / Q) - z) / (2.0 * (1.0 - z))
                for x in q]

    lo, hi = 0.0, 0.3
    for _ in range(80):
        z = (lo + hi) / 2.0
        if sum(probs(z)) > 1.0:
            lo = z
        else:
            hi = z
    return probs((lo + hi) / 2.0)


def novig(odds, metodo):
    if metodo == 'power':
        return novig_power(odds)
    if metodo == 'shin':
        return novig_shin(odds)
    return novig_proporcional(odds)


def kelly_fraction(p, o):
    """Fracao de Kelly cheia para odd decimal o e prob p (0 se sem edge)."""
    if o <= 1.0:
        return 0.0
    f = (p * o - 1.0) / (o - 1.0)
    return max(f, 0.0)
