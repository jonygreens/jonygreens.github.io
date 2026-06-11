#!/bin/sh
# Rode DEPOIS de criar a org "jonygreens" em https://github.com/organizations/plan (plano Free).
set -e
cd "$(dirname "$0")"
echo "1/3 criando jonygreens/jonygreens.github.io e fazendo push…"
gh repo create jonygreens/jonygreens.github.io --public --source=. --push \
  --description "Previsão de tênis com Elo calibrado — probabilidades, odd justa, EV e multi-ranking"
echo "2/3 ativando GitHub Pages…"
gh api repos/jonygreens/jonygreens.github.io/pages -X POST -f "source[branch]=main" -f "source[path]=/" || true
echo "3/3 derrubando o repo antigo (some da conta EduardoGuipa)…"
gh repo delete EduardoGuipa/tennis-elo-web --yes 2>/dev/null || {
  echo "   (sem escopo delete_repo — tornando privado, o que desliga o Pages antigo)"
  gh api repos/EduardoGuipa/tennis-elo-web -X PATCH -f visibility=private -F has_pages=false || true
}
echo "PRONTO: https://jonygreens.github.io (Pages leva ~2 min no 1º build)"
