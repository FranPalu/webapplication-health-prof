# M4 — Analisi preliminare supervisionata

M4 è disattivata per impostazione predefinita e l'analisi dei referti può essere attivata solo in ambiente DEBUG. Usare esclusivamente dati sintetici nel collaudo locale. Il professionista verificato con MFA e relazione di cura può aprire una versione di un referto in **Anagrafiche autorizzate → Documenti clinici → Analisi preliminare**. Avviare l'analisi e aggiornare la vista dopo il passaggio in coda.

Il professionista confronta le evidenze con il referto originale. **Accetta** attesta il testo proposto. **Modifica** permette di redigere e attestare il testo definitivo anche se il modello è indisponibile. **Rifiuta** richiede una motivazione e non produce un parere. La pubblicazione è separata ed è riservata all'autore della revisione. Il paziente collegato trova il risultato in **Pareri professionali pubblicati**. L'attestazione è interna al portale e registra autore, data e impronta SHA-256. Le bozze e le motivazioni di rifiuto sono cifrate, escluse dall'API paziente e da FHIR.

## Avvio locale

1. Creare la directory ignorata `.analysis-models` nella root. Salvare la variante Q4_K_M ufficiale come `qwen.gguf` e verificare l'hash riportato nel registro sottostante.
2. Eseguire `make env`, poi `CLINICAL_ANALYSIS_ENABLED=1 docker compose --env-file .env.dev --profile analysis up -d --build`. Il worker analisi consuma soltanto la coda dedicata. Celery Beat recupera i job in attesa e i lease scaduti ogni 15 secondi. Ogni job ha un massimo di tre tentativi.
3. Per tornare all'impostazione standard, fermare `analysis-worker` con il profilo analysis e riavviare con `make dev` senza la variabile d'ambiente.

Il PDF usa il testo incorporato pagina per pagina. Le pagine senza testo vengono rasterizzate e riconosciute con Tesseract. Sono supportati anche PNG e JPEG. Limiti di elaborazione M4 sono 12 pagine e 100 righe. L'estrattore v1 riconosce un insieme esplicito di analiti e unità. Le righe non riconosciute, gli intervalli assenti e i confronti ambigui vengono segnalati. Le regole confrontano esclusivamente gli intervalli riportati sul referto. La bozza registra, quando disponibile, la confidenza media delle parole riconosciute per pagina da Tesseract. La confidenza complessiva della pipeline resta non calibrata e ha valore nullo.

## Registro dei modelli

- **Tesseract tessdata_fast 4.1.0**, Apache-2.0. Modelli OCR `ita` SHA-256 `b8f89e1e785118dac4d51ae042c029a64edb5c3ee42ef73027a6d412748d8827` e `eng` SHA-256 `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`. Destinati all'OCR di referti leggibili. La qualità dipende da scansione e impaginazione. [Repository upstream](https://github.com/tesseract-ocr/tessdata_fast/tree/4.1.0)
- **Qwen2.5-1.5B-Instruct GGUF Q4_K_M**, Apache-2.0, revisione `dd26da4`, SHA-256 `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`. Seleziona righe già classificate da regole deterministiche. Il prompt contiene codici di analiti, riferimenti e classificazioni, senza testo OCR libero, valori o identificativi. Il server valida il JSON e compone il testo dai dati originali. Il runtime llama.cpp è fissato al commit `4762ad7316dcdec20016ab5985fb46a27902204d`, senza download in inferenza. [Pesi ufficiali](https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/blob/main/qwen2.5-1.5b-instruct-q4_k_m.gguf)
- **TorchXRayVision densenet121-res224-all**, checkpoint upstream release `v1`, SHA-256 `56524913dd16a906422e8d8b66a7a5c46be1d82eb7ac012d8103776f1aa68899`. Libreria Apache-2.0, con verifica distinta dei termini dei pesi e dei dataset richiesta prima di distribuirli. Solo collaudo tecnico di radiografie toraciche frontali. Il contenitore esegue l'artefatto verificato con rete disabilitata, filesystem in sola lettura e senza accesso al database o allo storage. I punteggi non sono calibrati per questa piattaforma. [Libreria e licenze](https://github.com/mlmed/torchxrayvision)

## Verifica

- Laboratorio reale: `docker compose --env-file .env.dev --profile analysis run --rm --no-deps analysis-worker python manage.py analysis_smoke`. Il comando genera PDF nativo e PDF scansionato sintetici, verifica F1, regole e presenza del riepilogo locale.
- Imaging reale: generare la fixture con `.venv/bin/python scripts/analysis-imaging-fixture.py`. Salvare il checkpoint upstream in `.analysis-models/xray.pt` e avviare `docker compose --env-file .env.dev --profile imaging-test run --rm --no-deps imaging-smoke`. Il manifest autorizza un solo file per hash, modalità e vista. Conservare eventuali report di test in un'area locale.
- Browser M4: usare la fixture sintetica del collaudo M3 e impostare `E2E_ANALYSIS=1`. Usare una fixture appena generata per il test `professional reviews a local analysis`, perché il flusso configura MFA.

## API e operatività

La risorsa `/api/v1/clinical/versions/{id}/analysis/` accoda e lista i job. `clinical/analysis/{id}/` legge l'esito, `review/` registra la decisione e `clinical/opinions/{id}/publish/` pubblica il parere. Il paziente legge da `clinical/patients/{id}/opinions/`. Un amministratore di tenant con MFA legge le metriche in `organizations/{id}/analysis/metrics/`. Le azioni cliniche usano l'autorizzazione diretta M3, anche se l'utente può vedere il documento via condivisione.

L'archiviazione o il purge del documento rende indisponibili gli esiti. Prima del rilascio su dati reali occorre definire e verificare la policy di conservazione e cancellazione delle copie derivate e dei backup, oltre alla revisione clinica, privacy, sicurezza e qualificazione regolatoria.
