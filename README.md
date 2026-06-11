# Jony Greens 🎾

Interface web do modelo de previsão de tênis baseado em Elo: probabilidades calibradas para ATP e WTA, comparação com odds de casas de aposta, metodologia completa e comparação com outros sistemas de rating.

**App publicado:** `https://jonygreens.github.io` (GitHub Pages; Render opcional via render.yaml)

## O que tem

- **Previsão** — escolha 2 jogadores, piso, formato (e altitude); o app calcula a probabilidade calibrada, a odd justa e — se você informar a odd da casa — o EV de cada lado, o stake Kelly ¼ e o **alerta de anti-sinal** (quando o modelo discorda demais do mercado, quem está errado costuma ser o modelo).
- **Rankings** — top 25 Elo atual por circuito, com Elo por piso.
- **Metodologia** — todas as fórmulas e parâmetros (K dinâmico 250/(m+5)^0.4, blend 50/50 geral/piso, escala de calibração 480, transformação best-of-5, camada de altitude) e a validação honesta em holdout intocado.
- **Comparação** — este modelo vs Elo clássico/FIDE, FiveThirtyEight, Tennis Abstract, Ultimate Tennis Statistics, Glicko-2, TrueSkill 2, WElo e a regressão sazonal do 538 — com o motivo técnico e o número medido de cada diferença.

## Stack

HTML + CSS + JavaScript puro (ES modules), **zero dependências e zero build** — a matemática do modelo (logística calibrada, transformação bo5 por bissecção, remoção de vig power, Kelly) roda inteira no navegador em `js/elo.js`. Os ratings chegam pré-computados em `data/atp.json` e `data/wta.json` (~75 KB cada), gerados pelo engine Python do projeto principal.

```
index.html        # as 4 abas
css/style.css     # tema escuro, responsivo, sem framework
js/elo.js         # núcleo do modelo (port de elo_core.py)
js/app.js         # UI: busca de jogadores, previsão, rankings
data/atp.json     # ratings ativos ATP (gerado pelo engine)
data/wta.json     # ratings ativos WTA
render.yaml       # blueprint do Render (static site)
```

## Rodar localmente

```bash
git clone https://github.com/jonygreens/jonygreens.github.io
cd tennis-elo-web
python3 -m http.server 8000
# abra http://localhost:8000
```

(Qualquer servidor estático serve — é preciso servir via HTTP por causa dos ES modules e do fetch dos JSONs.)

## Deploy no Render

O repositório tem `render.yaml` (blueprint). Para publicar:

1. [dashboard.render.com](https://dashboard.render.com) → **New → Blueprint** → conecte este repositório.
2. Confirme — o serviço `tennis-elo-lab` sobe como **Static Site** (grátis).
3. Todo push no `main` redeploya automaticamente.

## Atualizar os ratings

No projeto principal (`tennis-elo-lab`, privado/local):

```bash
cd ../tennis-elo-lab
git -C data/tennis_atp pull && git -C data/tennis_wta pull
python3 src/build_elo.py build
python3 scripts_export_web.py   # regenera data/*.json deste repo
cd ../tennis-elo-web && git commit -am "ratings $(date +%F)" && git push
```

## Crédito e licença

- Dados de partidas: [Jeff Sackmann / Tennis Abstract](https://github.com/JeffSackmann/tennis_atp) — **CC BY-NC-SA 4.0** (uso não-comercial com atribuição; este projeto é um estudo estatístico sem fins comerciais).
- Metodologia: ver aba Metodologia do app; decisões e validação documentadas no projeto principal.
- **Aviso:** este app não é recomendação de aposta. No backtest pré-registrado, apostar o modelo contra odds de fechamento teve ROI **negativo** (−5,5%). Jogue com responsabilidade (+18).
