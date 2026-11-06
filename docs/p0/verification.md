# P0 · Evidenze di verifica

Esecuzione locale del 6 novembre 2026, su dati sintetici. Baseline Git `50d3a59`. Le scansioni interrogano gli advisory disponibili al momento della verifica. La CI remota e i container di produzione restano fuori dal perimetro di prova.

## Risultati

| Controllo | Esito | Evidenza |
| --- | --- | --- |
| Django baseline, PostgreSQL 17 temporaneo | 48 passati, 1 skip, 79,31% | Soglia locale dell'80% fallita senza l'integrazione ClamAV/S3 |
| Django dopo correzioni, Compose con DB di test separato | 49 passati, nessuno skip, **82,42%** | 2.850 istruzioni coperte su 3.458 nel perimetro `identity`, esclusi test e migrazioni. 92% per `analysis_views.py`, 93% per `clinical_views.py`, 94% per `security.py`, 100% per `services.py`. Il gate globale ≥85% e 100% per tutte le regole rimane aperto |
| Playwright con account sintetici e ClamAV | 25 passati, 1 skip, poi 1 passato separatamente | 26 scenari complessivi, ripetuti sul lockfile corretto con Node 24. Per l'AI è stata ricreata la fixture MFA e invocato il task Django sui job del DB temporaneo. Il test prova blocco della bozza e pubblicazione del parere attestato. Firma elettronica e orchestrazione Celery completa sono fuori da questa prova |
| Suite Node e database storico | 22/22, controlli SQLite passati | V8 sui moduli caricati dai test Node: 100% righe, 86,01% rami, 96,69% funzioni. Le percentuali escludono il resto del frontend |
| Lint, format, type-check, build | Passati | Ruff, mypy su `config identity`, ESLint, TypeScript e build Next e Vinext. Prove iniziali su Node 22.22.2, ripetizione frontend con Node 24.22.2 richiesto dalla CI |
| Bandit 1.9.4 | 0 alti, 0 medi, 5 bassi | B404/B603 su subprocess OCR senza shell, due B101 su invarianti di paginazione e B105 sulla cancellazione del segreto MFA durante il reset |
| Semgrep 1.184.0, `p/typescript` | 0 rilevazioni | 74 regole su 37 file tracciati in `app` e `lib`. Il perimetro non comprende l'intero codice TypeScript |
| pip-audit 2.10.1 | 0 vulnerabilità note | Scan del file `backend/requirements.txt` con versioni pinnate e `--no-deps`. Dipendenze OS, immagini e pesi dei modelli fuori perimetro |
| pnpm audit produzione | 0 avvisi | Grafo lockfile `--prod` |
| pnpm audit completo | **0 alti o critici** dopo correzione, 6 moderati e 1 basso residui | Baseline con 62 avvisi, di cui 28 alti nel grafo di sviluppo. Versioni aggiornate e override in [ADR 0011](../adr/0011-p0-npm-advisories.md) |
| Migrazioni e contratto OpenAPI | Passati | `makemigrations --check --dry-run`, generazione OpenAPI senza warning e confronto identico con il file tracciato |
| Verifica mirata segreti | Nessuna corrispondenza | Semgrep `p/secrets` con 44 regole su 302 file tracciati, più pattern mirati per chiavi private, token AWS, GitHub e Stripe live. Cronologia e immagini fuori perimetro |

Il primo tentativo Playwright è stato bloccato dai permessi macOS sul processo Chromium. Il tentativo con browser abilitato e porte non allineate al rewrite compilato ha verificato i soli flussi demo/manifest. La prova finale usa il backend temporaneo sulla porta prevista dal build. Il DB isolato per il browser è stato distinto dal DB applicativo locale.

## Riproduzione

Configurare `.env.dev` con `make env` e usare uno stack locale dedicato a fixture. Avviare con `make dev`. Le variabili disponibili sono in [`.env.example`](../../.env.example).

```sh
make check
docker compose --env-file .env.dev run --rm -e CLINICAL_INTEGRATION_TEST=1 backend pytest
pnpm test
python3 tests/database_test.py
node --experimental-test-coverage --import tsx --test tests/*.test.ts
bandit -r backend/config backend/identity
semgrep scan --config p/typescript --metrics off app lib
pip-audit -r backend/requirements.txt --no-deps
pnpm audit --prod --audit-level high
pnpm audit --audit-level high
```

Per i browser, usare la procedura [CI](../../.github/workflows/ci.yml) per creare la fixture, salvandola in un file temporaneo. Eseguire la suite con `E2E_CLINICAL_FIXTURE`, `E2E_BASE_URL` e `MAILPIT_URL` oppure `E2E_MAIL_DIR`. Per lo scenario AI, ricreare la fixture e abilitare il percorso locale con `CLINICAL_ANALYSIS_ENABLED=1`, il worker di collaudo e `E2E_ANALYSIS=1`. Eliminare la fixture dopo il test. I valori di collaudo sono sintetici e il JSON temporaneo contiene credenziali usa e getta.

## Regressioni P0

- `test_folder_scope_includes_descendants_and_preserves_patient_boundary` prova confine delle cartelle, versione del consenso, accesso del concedente dopo cessazione della relazione, tentativo di ri-condivisione del non destinatario e audit.
- `test_analysis_review_publication_and_tenant_isolation` prova gate paziente ed estraneo sulle liste, audit del lettore autorizzato, visibilità prima/dopo la pubblicazione e assenza del payload di bozza nella risposta paziente.
- `test_clinical_version_lifecycle_and_access` verifica che utenti senza diritto non ricevano il file. I test della catena DB verificano modifica e cancellazione ordinarie, concatenazione e scritture concorrenti. Restano aperti TRUNCATE privilegiato, separazione dei ruoli DB e checkpoint esterno.
