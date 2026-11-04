# M3 — Documenti clinici

Avviare con `make dev`. Compose avvia PostgreSQL, SeaweedFS, ClamAV e i processi Celery. Su Apple Silicon l'immagine ClamAV 1.4 usa emulazione amd64. Attendere che ClamAV abbia caricato le firme prima del primo upload. La configurazione locale genera le chiavi mancanti in .env.dev e conserva quelle esistenti.

## Portale e permessi

Nel portale autenticato aprire **Anagrafiche autorizzate → Documenti clinici**. Un professionista verificato con appartenenza attiva e relazione di cura può caricare documenti e creare cartelle. L'autore può aggiungere versioni o archiviare il documento finché conserva l'accesso. La cronologia espone le versioni scaricabili. Cercare per titolo o per parole esatte nel testo estratto dai PDF. Le scansioni PDF senza testo, le immagini e DICOM sono ricercabili per titolo. Il demo agenda usa il proprio campione di dati fittizi.

Le condivisioni di documento includono le versioni future. Le cartelle includono i discendenti e la cartella clinica include anche i referti strutturati. L'API verifica il consenso v2 su ciascun grant e sui suoi antenati. Gli accessi legacy all'anagrafica seguono il consenso M2. Una nota psicologica è visibile soltanto all'autore con una relazione di cura attiva. Il controllo vale per ricerca, cronologia, download e FHIR. Le attività su queste note sono escluse dallo storico del paziente. Un permesso download viene verificato a ogni richiesta.

## API

Tutti i percorsi sono sotto /api/v1. Le scritture richiedono sessione e CSRF.

- GET/POST clinical/patients/{patient}/folders/ elenca o crea cartelle. In creazione passare title e parent_folder facoltativo.
- GET/POST clinical/patients/{patient}/documents/ elenca le versioni correnti o crea un documento. GET accetta q. POST accetta multipart con file, title, kind e folder facoltativo. I tipi documentali sono report, nutrition, psychology e other.
- GET/POST/DELETE clinical/documents/{document}/ elenca la cronologia, aggiunge una versione o archivia tutte le versioni.
- GET clinical/versions/{version}/download/ restituisce un allegato dopo il controllo di accesso.
- POST shares/ con scope item e document, oppure scope folder e folder, crea una richiesta di consenso. Le richieste chart coprono l'intero ambito clinico.
- POST clinical/patients/{patient}/reports/ accetta code (LOINC), title, effective_at e observations con code, display, value e unit.
- GET fhir/metadata espone le capacità FHIR R4. GET fhir/{tipo}/{id} espone letture per Patient, Practitioner, Organization, Consent, DiagnosticReport, Observation e DocumentReference. Il client può richiedere application/fhir+json. I riferimenti all'anagrafica vengono omessi se l'utente non può leggere il relativo Patient. I codici LOINC inseriti sono controllati per sintassi. La verifica contro un server terminologico e la validazione dei profili d'integrazione restano attività di integrazione.

## Storage e conservazione

Il server ammette PDF, PNG, JPEG e DICOM con preambolo, fino a 10 MiB. Verifica firma, ClamAV e struttura. Un errore dello scanner blocca il caricamento. DICOM viene verificato fino ai metadati, senza decodificare i pixel. I PDF protetti e quelli oltre 250 pagine vengono rifiutati. Il contenuto viene consegnato come allegato. La ricerca usa impronte HMAC per tenant delle parole estratte dai PDF, con una chiave dedicata. I titoli restano in chiaro nel database per la ricerca. Usare titoli generici.

Ogni versione usa una chiave di cifratura propria. Fuori da DEBUG, configurare CLINICAL_KMS_KEY_ID con una chiave simmetrica AWS KMS e credenziali IAM dell'ambiente. Il contesto KMS contiene il solo UUID del tenant. In locale il backend deriva una chiave di avvolgimento per tenant da CLINICAL_MASTER_KEY. Conservare chiavi e backup separatamente.

Il database conserva temporaneamente i binari cifrati e costituisce la coda durevole di trasferimento. Il worker scrive in S3 sotto una chiave deterministica, poi salva il riferimento e rimuove il binario dal database. Il job periodico riprende le scritture interrotte. Usare un bucket privato e monitorare il numero di versioni con object_key vuoto.

I comandi seguenti si eseguono con `docker compose --env-file .env.dev exec backend python manage.py clinical_storage` seguito dall'operazione.

- `offload` riconcilia le versioni in attesa. `verify` legge e verifica dimensione e hash.
- `rotate --tenant UUID` mostra i candidati. Aggiungere `--apply` per riavvolgere le chiavi. In locale aggiungere la vecchia chiave a CLINICAL_PREVIOUS_MASTER_KEYS, impostare la nuova chiave primaria, riavviare e verificare prima di rimuovere il fallback. Conservare le vecchie chiavi richieste dai backup.
- `hold --tenant UUID --document UUID --apply` blocca la cancellazione. `release-hold` rimuove il blocco con gli stessi argomenti.
- `purge --tenant UUID --days N` conta le versioni archiviate eleggibili. Dopo revisione della policy del tenant, `--apply` elimina le copie S3 e cancella chiave, contenuto, titolo e indice della versione. Conserva il minimo riferimento per l'audit. Nessuna cancellazione automatica è programmata. Il ruolo operativo richiede permessi di cancellazione di versioni S3 quando il bucket è versionato.

Per un backup coordinato sospendere scritture, worker e purge. Salvare PostgreSQL, tutte le chiavi S3 referenziate e le chiavi di decifratura in ambienti separati. Per il restore usare un database e un bucket isolati, ripristinare le stesse chiavi degli oggetti, configurare l'accesso alle chiavi crittografiche e lanciare `clinical_storage verify` prima di riabilitare scritture o purge. Ripetere il controllo dell’audit e i test di accesso. La prova locale ha ripristinato un dump PostgreSQL e gli oggetti cifrati in un database e un bucket separati. Il controllo dell’hash del PDF sintetico e la verifica della catena di audit sono passati.

## Importazione R2

Esportare e verificare prima la mappatura delle anagrafiche. Preparare un manifest JSONL con source, owner, patient_legacy_id, organization, author, key, sha256, title e kind facoltativo. Il professionista identificato da author deve avere accesso alla cartella del paziente importato. La chiave R2 deve iniziare con owner seguito da /. Configurare le quattro variabili LEGACY_R2 con credenziali di sola lettura. Rendere il manifest disponibile al container e lanciare `python manage.py import_legacy_documents manifest.jsonl`. Il comando confronta gli hash e verifica tutti i file. Ripetere con `--apply` per scrivere. Un errore ferma il comando. Una nuova esecuzione riconosce le righe già importate con lo stesso paziente e hash. Gli oggetti sorgente rimangono su R2.

## Test

Eseguire la suite con `docker compose --env-file .env.dev run --rm -e CLINICAL_INTEGRATION_TEST=1 backend pytest -p no:cacheprovider`. Il test di integrazione usa PDF sintetico, firma EICAR, SeaweedFS e wrapping locale. Le verifiche sul provider AWS e su un bucket R2 reale richiedono credenziali e configurazione esterne. I testi di consenso seed richiedono revisione prima dell'uso operativo.

Per la prova nel browser creare il file di fixture in una directory temporanea con permessi privati:

```sh
fixture="$(mktemp)"
trap 'rm -f "$fixture"' EXIT
docker compose --env-file .env.dev exec -T backend python manage.py shell -v 0 \
  < backend/tests/clinical_browser_fixture.py > "$fixture"
E2E_CLINICAL_FIXTURE="$fixture" E2E_BASE_URL=http://localhost:8080 \
  MAILPIT_URL=http://localhost:8025 pnpm test:e2e
```
