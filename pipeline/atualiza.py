# -*- coding: utf-8 -*-
"""
Pipeline de atualizacao do Jony Greens — roda local ou no GitHub Actions.

  python3 pipeline/atualiza.py ratings     # recalcula os 4 modelos de Elo (precisa dos CSVs Sackmann)
  python3 pipeline/atualiza.py ta          # scrape do snapshot Tennis Abstract (uso pessoal, com atribuicao)
  python3 pipeline/atualiza.py polymarket  # snapshot dos mercados de tenis do Polymarket

Dados Sackmann: clona/usa em $SACKMANN_DIR (default ./_dados). Licenca CC BY-NC-SA 4.0 —
este projeto e pessoal e nao-comercial, com atribuicao no site.
"""
import json
import os
import re
import sys
import datetime
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import elo_core as ec

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DADOS = os.environ.get('SACKMANN_DIR', os.path.join(RAIZ, '_dados'))
SAIDA = os.path.join(RAIZ, 'data')

# Os 4 modelos: nosso (calibrado) + reimplementacoes vivas das formulas alheias.
# Cada um carrega a escala da PROPRIA previsao (o app usa isso ao comparar).
MODELOS = {
    'nosso': dict(rotulo='Jony Greens v2.1', escala_app=480, blend_app=0.5, bo5_app=True,
                  cfg={}),
    'uts': dict(rotulo='UTS (reimpl. kFunction)', escala_app=400, blend_app=0.5, bo5_app=False,
                cfg={'k_modelo': 'uts', 'escala_prob': 400.0}),
    'f538': dict(rotulo='FiveThirtyEight (reimpl.)', escala_app=400, blend_app=1.0, bo5_app=False,
                 cfg={'escala_prob': 400.0, 'peso_blend_geral': 1.0, 'ajuste_bo5': 'nenhum'}),
    'classico': dict(rotulo='Elo clássico K=32', escala_app=400, blend_app=1.0, bo5_app=False,
                     cfg={'k_base': 32, 'k_offset': 0, 'k_shape': 0,
                          'escala_prob': 400.0, 'peso_blend_geral': 1.0, 'ajuste_bo5': 'nenhum'}),
}

BASE_CFG = {
    'rating_inicial': 1500, 'k_base': 250, 'k_offset': 5, 'k_shape': 0.4,
    'mult_k_slam': 1.0, 'mult_k_masters': 1.0, 'mult_k_davis': 1.0,
    'incluir_davis': True, 'incluir_challengers': True, 'incluir_futures': False,
    'peso_blend_geral': 0.5, 'iniciar_superficie_do_geral': True,
    'carpet_vira': 'geral_apenas', 'contar_retirements': False, 'contar_walkovers': False,
    'dias_inatividade': 56, 'boost_k_retorno': 1.5, 'partidas_boost_retorno': 20,
    'penalidade_retorno_pts': 0, 'ajuste_bo5': 'transformacao_sets_iid', 'mov': 'nenhum',
    'escala_prob': 480.0, 'entrada_por_rank': True, 'set_elo_peso': 0.25,
    'lesao_penalidade_pts': 80, 'lesao_partidas': 6,
}


def hoje():
    return datetime.date.today().isoformat()


def cmd_ratings():
    for tour in ('atp', 'wta'):
        repo = os.path.join(DADOS, 'tennis_%s' % tour)
        if not os.path.isdir(repo):
            sys.exit('faltam dados: %s (clone JeffSackmann/tennis_%s)' % (repo, tour))
        matches = ec.load_matches(repo, tour, 1968, datetime.date.today().year,
                                  include_qual_chall=True, include_futures=False,
                                  carpet_as='geral_apenas', count_walkovers=False,
                                  count_retirements=False)
        max_od = max(m[1] for m in matches)
        corte = datetime.date.fromordinal(max_od).isoformat()
        lim = (datetime.date.fromordinal(max_od) - datetime.timedelta(days=365)).isoformat()
        saida = {'data_corte': corte, 'gerado_em': hoje(), 'modelos': {}}
        for chave, m in MODELOS.items():
            cfg = dict(BASE_CFG)
            cfg.update(m['cfg'])
            state, _ = ec.run_elo(matches, cfg)
            jog = []
            for pid, elo in state['r'].items():
                if state['n'].get(pid, 0) < 30:
                    continue
                ult = state['last'].get(pid)
                ult = datetime.date.fromordinal(ult).isoformat() if ult else ''
                if ult < lim:
                    continue
                jog.append({'n': state['names'].get(pid, str(pid)), 'e': round(elo, 1),
                            's': {s[0]: round(state['rs'][(pid, s)], 1)
                                  for s in ('Hard', 'Clay', 'Grass') if (pid, s) in state['rs']},
                            'm': state['n'][pid], 'r': state['lastrank'].get(pid), 'u': ult})
            jog.sort(key=lambda x: -x['e'])
            saida['modelos'][chave] = {'rotulo': m['rotulo'], 'escala': m['escala_app'],
                                       'blend': m['blend_app'], 'bo5': m['bo5_app'],
                                       'jogadores': jog}
            print('%s/%s: %d jogadores' % (tour, chave, len(jog)))
        with open(os.path.join(SAIDA, 'modelos_%s.json' % tour), 'w', encoding='utf-8') as f:
            json.dump(saida, f, ensure_ascii=False, separators=(',', ':'))
        # compat: data/{tour}.json continua sendo o modelo principal
        nosso = saida['modelos']['nosso']
        with open(os.path.join(SAIDA, '%s.json' % tour), 'w', encoding='utf-8') as f:
            json.dump({'tour': tour, 'data_corte': corte,
                       'jogadores': nosso['jogadores']}, f, ensure_ascii=False, separators=(',', ':'))


def _baixa(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (JonyGreens pessoal)'})
    return urllib.request.urlopen(req, timeout=40).read().decode('utf-8', 'ignore')


def cmd_ta():
    for tour in ('atp', 'wta'):
        html = _baixa('https://tennisabstract.com/reports/%s_elo_ratings.html' % tour)
        atual = re.search(r'Last update:\s*([\d-]+)', html)
        corpo = html.split('<tbody>', 1)[1].split('</tbody>', 1)[0]
        jog = []
        for linha in re.findall(r'<tr>(.*?)</tr>', corpo, re.S):
            tds = [re.sub(r'<[^>]+>', '', t).replace('&nbsp;', ' ').strip()
                   for t in re.findall(r'<td[^>]*>(.*?)</td>', linha, re.S)]
            if len(tds) < 11 or not tds[3]:
                continue
            try:
                jog.append({'n': tds[1], 'e': float(tds[3]),
                            's': {k: float(v) for k, v in
                                  (('H', tds[6]), ('C', tds[8]), ('G', tds[10])) if v}})
            except ValueError:
                continue
        with open(os.path.join(SAIDA, 'ta_%s.json' % tour), 'w', encoding='utf-8') as f:
            json.dump({'fonte': 'tennisabstract.com (Jeff Sackmann) — snapshot p/ uso pessoal, com atribuição',
                       'atualizado': atual.group(1) if atual else hoje(),
                       'capturado_em': hoje(), 'jogadores': jog},
                      f, ensure_ascii=False, separators=(',', ':'))
        print('ta_%s: %d jogadores (update %s)' % (tour, len(jog), atual.group(1) if atual else '?'))


def cmd_polymarket():
    eventos, offset = [], 0
    try:
        while offset < 600:
            lote = json.loads(_baixa(
                'https://gamma-api.polymarket.com/events?tag_slug=tennis&closed=false&limit=100&offset=%d' % offset))
            if not lote:
                break
            eventos.extend(lote)
            offset += 100
    except Exception as e:
        print('polymarket indisponivel (%s) — mantendo snapshot anterior' % e)
        return
    partidas = []
    for ev in eventos:
        for mk in ev.get('markets', []):
            try:
                precos = json.loads(mk.get('outcomePrices') or '[]')
                nomes = json.loads(mk.get('outcomes') or '[]')
            except Exception:
                continue
            if len(precos) != 2 or len(nomes) != 2:
                continue
            partidas.append({'t': ev.get('title', ''), 'slug': ev.get('slug', ''),
                             'lados': nomes, 'precos': [float(p) for p in precos],
                             'volume': round(float(mk.get('volumeNum') or 0))})
    with open(os.path.join(SAIDA, 'polymarket.json'), 'w', encoding='utf-8') as f:
        json.dump({'capturado_em': datetime.datetime.utcnow().isoformat() + 'Z',
                   'mercados': partidas}, f, ensure_ascii=False, separators=(',', ':'))
    print('polymarket: %d mercados' % len(partidas))


def cmd_provisorio():
    """Jogos que ACABARAM (mercados resolvidos no Polymarket) viram updates provisorios
    de Elo geral ate o proximo sync da fonte oficial. Conservador: so aplica quando os
    DOIS lados casam com exatamente 1 jogador ativo cada."""
    corte = {}
    for tour in ('atp', 'wta'):
        base = json.load(open(os.path.join(SAIDA, '%s.json' % tour)))
        corte[tour] = base['data_corte']
    eventos, offset = [], 0
    try:
        while offset < 1000:
            lote = json.loads(_baixa('https://gamma-api.polymarket.com/events?tag_slug=tennis&closed=true&order=endDate&ascending=false&limit=100&offset=%d' % offset))
            if not lote:
                break
            eventos.extend(lote)
            offset += 100
    except Exception as e:
        print('polymarket indisponivel (%s)' % e)
        return
    import unicodedata
    def norm(x):
        x = unicodedata.normalize('NFKD', x)
        return ''.join(c for c in x if not unicodedata.combining(c)).lower()
    for tour in ('atp', 'wta'):
        base = json.load(open(os.path.join(SAIDA, '%s.json' % tour)))
        idx = {}
        for j in base['jogadores']:
            idx.setdefault(norm(j['n'].split()[-1]), []).append(j)
        deltas, vistos = {}, set()
        for ev in eventos:
            slug = ev.get('slug', '')
            if not slug.startswith(tour + '-') or ev.get('endDate', '')[:10] <= corte[tour]:
                continue
            for mk in ev.get('markets', []):
                try:
                    precos = [float(p) for p in json.loads(mk.get('outcomePrices') or '[]')]
                    lados = json.loads(mk.get('outcomes') or '[]')
                except Exception:
                    continue
                if len(precos) != 2 or sorted(precos) != [0.0, 1.0] or slug in vistos:
                    continue
                cand = [idx.get(norm((l or '').split()[-1]), []) for l in lados]
                if len(cand[0]) != 1 or len(cand[1]) != 1 or cand[0][0]['n'] == cand[1][0]['n']:
                    continue
                vistos.add(slug)
                venc = cand[0][0] if precos[0] == 1.0 else cand[1][0]
                perd = cand[1][0] if precos[0] == 1.0 else cand[0][0]
                ev_p = 1.0 / (1.0 + 10 ** ((perd['e'] - venc['e']) / 400.0))
                kv = 250.0 / ((venc['m'] + 5) ** 0.4)
                kp = 250.0 / ((perd['m'] + 5) ** 0.4)
                deltas[venc['n']] = deltas.get(venc['n'], 0) + kv * (1 - ev_p)
                deltas[perd['n']] = deltas.get(perd['n'], 0) - kp * (1 - ev_p)
        with open(os.path.join(SAIDA, 'provisorio_%s.json' % tour), 'w', encoding='utf-8') as f:
            json.dump({'desde': corte[tour], 'gerado_em': datetime.datetime.utcnow().isoformat() + 'Z',
                       'n_jogos': len(vistos), 'deltas': {k: round(v, 1) for k, v in deltas.items()}},
                      f, ensure_ascii=False, separators=(',', ':'))
        print('provisorio_%s: %d jogos resolvidos, %d jogadores ajustados' % (tour, len(vistos), len(deltas)))


if __name__ == '__main__':
    {'ratings': cmd_ratings, 'ta': cmd_ta, 'polymarket': cmd_polymarket, 'provisorio': cmd_provisorio}[sys.argv[1]]()
