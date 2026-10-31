# Poolstat

Statický přehled bazénů. Zdroje, pravidelné rozvrhy a dostupné datové feedy
jsou v `config/pools.json`; publikovaný snímek je `data/pools.json`.

## Denní aktualizace a nasazení

Stávající workflow `.github/workflows/pages.yml` běží každý den v **06:00
Europe/Prague**, tedy včetně přechodu mezi letním a zimním časem. GitHub může
plánovaný běh při vytížení zpozdit. Stejný postup spouští push na `main`;
jednorázově jej lze spustit také přes Actions → Pool status update → Run workflow.

1. Spustí Python a browserové regresní testy.
2. Stáhne všechny aktivní bazény podle konfigurace do `.tmp/pools.candidate.json`.
3. Ověří aktuálnost, úspěšné načtení všech oficiálních zdrojů a platnost všech
   nakonfigurovaných feedů drah včetně dnešního rozpisu. Ověří i vykreslení kandidáta.
4. Teprve po úspěšných kontrolách nahradí `data/pools.json` a při změně vytvoří
   commit účtem `github-actions[bot]` a pushne jej na `main`.
5. Ze stejného ověřeného snímku připraví a nasadí GitHub Pages. Browserový test
   nasazeného webu kontroluje i shodu času aktualizace s právě vytvořeným snímkem.

Commit vytvořený pomocí `GITHUB_TOKEN` sám nespouští další push workflow;
nasazení proto pokračuje ve stejném běhu. Pull requesty nevytvářejí datové commity
ani nenasazují web. K zápisu je potřeba `contents: write`, pro Pages také
`pages: write` a při nasazování `id-token: write`. Pokud ochrana větve zápis
botovi zakazuje, krok push selže a nasazení se neprovede.

Chyba načítání nebo validace ukončí aktualizaci neúspěšně. Předchozí verzovaná
data i nasazený web zůstanou zachované. Generátor navíc zapisuje až po validaci
a soubor nahrazuje atomicky. Případné problémy sledujte v Actions.

Výšinka v Turnově poskytuje veřejný Google kalendář programu, ale ne obsazenost
jednotlivých drah. Proto nemá `lane_feed_url`; nepřítomnost živého rozpisu drah
u tohoto bazénu není chyba aktualizace. Stávající údaj `free_lanes_when_open`
je hodnota z konfigurace, nikoli výsledek načtení obsazenosti z kalendáře.

## Místní ověření

Použijte Python 3.12, Node.js 22 a Chromium pro Playwright; závislosti instalujte
z `requirements.txt` a přes `npm ci`. Pro systémový Chromium lze nastavit
`CHROMIUM_EXECUTABLE_PATH`.

```sh
python -m unittest discover -s tests -v
npm test
python scripts/update_data.py --output .tmp/pools.candidate.json
python scripts/check_links.py --require-live --data .tmp/pools.candidate.json
DATA_FILE=.tmp/pools.candidate.json npm test
```
