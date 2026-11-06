# P1 · Evidenze di verifica

Verifiche locali del 6 novembre 2026 su dati sintetici, con Node 24.22.2 e stack Compose locale. GitHub Actions configurata per le stesse famiglie di controlli. Esecuzione remota da verificare al push.

| Controllo | Risultato |
| --- | --- |
| Verifica registro e inventario | 18 hazard, 20 requisiti, 991 voci SOUP. Riferimenti ai test Python risolti e versioni npm/Python dichiarate coperte |
| Unit test del gate | 4 passati. Sono provati registro valido, riferimenti non risolti, rifiuto di rischio bloccante e rifiuto di accettazione priva di riferimenti |
| Gate di rilascio clinico | Rifiuto atteso, exit 1. Tutti i 18 hazard sono bloccanti |
| Django senza integrazione documentale | 48 passati e 1 skip atteso con `--no-cov` |
| Django con ClamAV e S3 | 49 passati, nessuno skip, 82,42% su `identity`. Target globale 85% ancora aperto |
| Node, SQLite e build | 22 test Node passati, controlli SQLite passati, build Next riuscita |
| Playwright | 25 scenari passati più 1 AI passato con fixture nuova. L'AI usa il task di analisi contro il DB sintetico, con ClamAV e pubblicazione di un parere attestato internamente |
| Lint e type-check | Ruff, format e mypy per QMS e Django, ESLint e TypeScript passati |
| Bandit 1.9.4 | Gate medio/alto passato, zero rilevazioni nel perimetro del gate |
| Semgrep 1.184.0 | 111 regole, zero rilevazioni dopo correzione delle tre entità JSX nella demo. Ruleset `p/typescript` e `p/secrets`. Scansione dei percorsi applicativi e dello script QMS, con esclusioni standard |
| SCA Python backend | pip-audit senza avvisi sulle dipendenze backend |
| SCA npm | Zero alti o critici, sei moderati e uno basso nel lockfile completo |
| SCA immagine imaging di collaudo | 28 righe advisory su pip 25.0.1, torch 2.7.1 (build CPU osservata) e setuptools 78.1.0, 19 ID distinti per pacchetto. Verifica metadata sulle versioni osservate. Remediation e regressione obbligatorie prima del riuso in P4 |

L'immagine imaging fa parte del profilo esplicito `imaging-test`. Il container di collaudo è senza rete, in sola lettura, con pesi verificati per hash. L'isolamento è un controllo temporaneo. La decisione di rilascio rimane bloccata e gli advisory restano aperti. SCA di OS/immagini di rilascio, verifica di firme cliniche, DPIA e validazione clinica indipendente sono prove distinte.

## Riproduzione

```sh
make dev
make check
make test
python3 scripts/check_qms.py
python3 scripts/check_qms.py --release
```

L'ultima invocazione è una prova negativa attesa. Per SAST/SCA usare gli strumenti e le versioni della [CI](../../.github/workflows/ci.yml). Per i browser usare fixture e procedura sintetica delle [evidenze P0](../p0/verification.md), con l'AI in esecuzione separata. Per verificare l'immagine imaging, estrarre le distribuzioni con `importlib.metadata` e interrogare gli advisory sulle versioni osservate usando `pip-audit --disable-pip --no-deps`. Conservare report, perimetro, digest e data della fonte come evidenze di configurazione.
