# Verifica P4 · 9 novembre 2026

I log testuali archiviati normalizzano soltanto spazi finali e ritorni di carrello; i risultati XML/JSON sono conservati e verificati per hash.

Stato: **parziale**, verificato nel perimetro tecnico sintetico. Non autorizza uso clinico. [Sintesi elaborabile](evidence/summary.json), [hash dei risultati](evidence/sha256.json), [tracciabilità](traceability.md), [limiti](../12-supervised-ai-p4.md).

## Risultati eseguiti

- Django/PostgreSQL con integrazione ClamAV/storage attiva: **265 passati**, nessuno saltato, copertura statement `identity` **86,88%**. [JUnit](evidence/django.xml), [coverage XML](evidence/coverage.xml), [esito completo](evidence/django.txt).
- Calcolatori: 4 test, **100% linee e branch**. [Prova](evidence/calculators.txt). `analysis.py`, `analysis_registry.py` e `analysis_signing.py` raggiungono 100% delle linee nella suite; questo non dimostra 100% dei branch o di tutte le autorizzazioni della piattaforma. Quest'ultimo criterio globale resta aperto.
- Frontend con Node 24: ESLint, TypeScript, **22 test Node**, build Next riusciti. [Log](evidence/node.txt). Tipi API rigenerati dopo schema OpenAPI validato senza warning.
- Browser Chromium: **26 passati e un test AI saltato nella suite generale**, poi quel test eseguito separatamente con **1 passato**, OCR/Qwen reali e fixture nuova. Tutti i 27 scenari sono quindi stati eseguiti. [Generale](evidence/browser.txt), [AI](evidence/browser-ai.txt). La prova AI dimostra il blocco del paziente prima della firma, non una firma PAdES/CAdES reale.
- QMS: checker riferimenti/SOUP riuscito e 4 unit test passati. Contratto imaging: 1 test con sottocasi negativi passato. Conversione: 1 test di checkpoint alterato passato nel container; confronto forward legacy/tensori e vettore smoke identico. [Conversione](evidence/conversion.txt), [regressione](evidence/conversion-test.txt), [smoke imaging](evidence/imaging-smoke.json).
- Migrazione 0037: applicazione, rollback a 0036 e riapplicazione riusciti su DB separato; nessuna migrazione mancante. [Esito](evidence/migration.txt).
- Compose valido; tentativo TCP esterno dal worker di laboratorio rifiutato. [Prova](evidence/network.txt). Il collaudo non dimostra isolamento o disponibilità produttivi.

## Sicurezza e dipendenze

[pip-audit backend](evidence/python-audit.json): nessun advisory noto. [npm](evidence/npm-audit.json): zero alti/critici, 6 moderati e 1 basso ancora aperti nel grafo completo. [Inventario imaging](evidence/imaging-after.json) con PyTorch 2.14.1+cpu, torchvision 0.29.2+cpu, pip 26.2 e setuptools 84.1.0: [nessun advisory noto](evidence/imaging-audit-after.json). Il [prima](evidence/imaging-audit-before.json) conserva gli advisory risolti; nessun ID è stato ignorato dalla scansione dipendenze. La scansione OS/container completa resta P10.

[Semgrep](evidence/semgrep.json): zero rilievi con regole TypeScript e segreti, inclusi nuovi file tracciati. [Bandit gate medio/alto](evidence/bandit.json): zero rilievi. La [scansione completa](evidence/bandit-all.json) mantiene 5 rilievi bassi riesaminati:

- B404/B603 in `analysis_pipeline.py`: esecuzione di comandi fissi con lista di argomenti, senza shell, timeout e ambiente ridotto; il testo non controlla il programma eseguito. I limiti del parser e l'isolamento produttivo restano da approfondire.
- Due B101 in `clinical_views.py`: assert sul risultato della paginazione per restringere il tipo, successivi all'autorizzazione; non sono condizioni di accesso o controllo di sicurezza.
- B105 in `views.py`: stringa vuota per cancellare il segreto MFA durante reset autenticato; non è una credenziale incorporata.

Una sola esclusione puntuale **B614** è dichiarata nel convertitore legacy in quarantena. Il gate conta un test statico escluso. [Motivazione e limiti](imaging-preparation.md): unico hash, nessun input paziente, rete/DB assenti, caricamento vietato nel runner di inferenza, rifiuto dei file alterati testato. Non si dichiara assenza assoluta di segreti o vulnerabilità sulla base dei soli scanner.

## Valutazione reale su fonti sintetiche

[Report](evidence/evaluation.json): cinque righe per quattro rendering. F1 esatto delle righe: nativo **1,00**, scansionato **1,00**, rotazione 3° **0,80**, sfocatura/riduzione **1,00**. Qwen pinnato ha restituito riferimenti validi e il server ha reso soltanto valori strutturati. I riquadri risultano presenti. Una riga su cinque viene persa o alterata nella rotazione: questa è una limitazione aperta, non un esito clinicamente accettato.

Sensibilità, specificità, PPV, NPV, AUC, calibrazione, IC clinici e sottogruppi sono nulli/non stimabili. Le fixture non hanno popolazione rappresentativa, diagnosi di riferimento o età/sesso. Non deriviamo metriche diagnostiche dall'F1 di estrazione.

## Ripetere le verifiche

```sh
python3 scripts/check_qms.py
python3 -m unittest discover -s tests -p qms_test.py
python3 -m unittest discover -s infra/imaging -p test_contract.py
python3 scripts/backend.py ../.venv/bin/mypy config identity
.venv/bin/ruff check backend infra/imaging
.venv/bin/ruff format --check backend infra/imaging
docker compose --env-file .env.dev run --rm -e CLINICAL_INTEGRATION_TEST=1 backend pytest -p no:cacheprovider
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

Usare Node 24 e `make dev` dopo le modifiche per ricostruire le immagini. Per i modelli reali seguire [P4](../12-supervised-ai-p4.md) e [preparazione imaging](imaging-preparation.md). Per il browser generare la fixture con `backend/tests/clinical_browser_fixture.py` tramite `manage.py shell -v 0`, conservare il JSON soltanto in file temporaneo protetto, impostare `E2E_CLINICAL_FIXTURE`, `E2E_BASE_URL` e `MAILPIT_URL`; eseguire `pnpm exec playwright test`. Usare una fixture nuova, `E2E_ANALYSIS=1` e `-g 'professional reviews local analysis'` per la prova AI. La fixture preapprova il manifest esclusivamente per test sintetici. Non committare credenziali o trace browser.

La CI aggiunge job distinti per OCR/Qwen e dipendenze dell'immagine imaging, oltre alle regressioni ordinarie. Il file YAML e i comandi sono verificati localmente; **la CI remota non è stata eseguita** in questa sessione.

## Gate e prossimo passo

`python3 scripts/check_qms.py --release` deve fallire e fallisce per gli hazard aperti. [Esito atteso](evidence/release-gate.txt). Firma reale/conservazione, dataset clinici, licenze dei pesi, OOD/calibrazione/localizzazione, drift validato, organizzazione della vigilanza e validazioni clinico-legali restano prerequisiti. Nessuna dichiarazione di conformità o marcatura CE.

P5 non è iniziata. Dipende da contratti FHIR, fonti ufficiali aggiornate, credenziali/accordi reali soltanto quando disponibili e validator in CI; i gate di sicurezza P4 devono rimanere vincolanti sulle future integrazioni.
