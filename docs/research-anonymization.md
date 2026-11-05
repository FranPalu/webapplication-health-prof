# M7 — Dati aggregati per la ricerca

## Consenso e proiezione

Nel portale il paziente collegato può concedere e revocare un consenso separato per le statistiche aggregate su osservazioni di laboratorio. Gli eventi registrano versione, attore, esito e data e sono append-only. Se cambia il collegamento del paziente, il consenso del precedente account non vale per la proiezione.

L'ETL raggruppa per anno e codice LOINC approvato. Conta account distinti mediante un HMAC derivato con separazione di dominio dalla chiave dell'applicazione. Il token esiste solo nella query clinica. Nessun token, valore analitico, identificatore, sede o data esatta viene scritto nell'archivio di ricerca. Le celle con meno di dieci account sono soppresse. Il comando `research_preview` conta le celle ammesse e soppresse per controllo operativo.

## Archivio e terminologie

Configurare RESEARCH_DATABASE_DSN verso una base PostgreSQL dedicata con un ruolo di scrittura riservato all'ETL. Il comando rifiuta un database con lo stesso nome di quello clinico. `python manage.py research_refresh` sostituisce atomicamente la proiezione fissa `laboratory-account-counts-v1`. Il checksum evita duplicati nel replay. Celery ripete il refresh ogni cinque minuti quando è configurato il DSN. Un refresh riuscito elimina anche le celle scese sotto soglia dopo una revoca.

Caricare un manifest revisionato con `python manage.py research_import_terms manifest.json`. Il comando valida senza scrivere per default. Usare `--apply` per importare. Ogni voce contiene system (loinc, snomed-ct o icd-10), code, version, source, license, active facoltativo e loinc_target facoltativo. La proiezione include solo codici LOINC attivi e sintatticamente validi. I lookup SNOMED CT e ICD-10 conservano la provenienza e la mappatura indicata dall'operatore. Non è inclusa la distribuzione dei dizionari terminologici completi. Verificare i termini dei materiali prima dell'importazione. [Licenza LOINC](https://loinc.org/license/)

Il catalogo espone la definizione della proiezione e il suo dizionario. Le colonne sono year, code e accounts. Year è l'anno calendario del referto. Code è il codice LOINC approvato. Accounts è il numero di account distinti con consenso valido.

## Approvazioni, dashboard ed export

Configurare RESEARCH_READ_DSN con un ruolo separato in sola lettura e impostare RESEARCH_EXPORT_ENABLED=1 dopo aver revisionato i dati sintetici di collaudo. L'export è disattivato per default. Un amministratore con MFA di un'organizzazione di ricerca presenta la finalità nel portale. Un amministratore di piattaforma diverso dal richiedente può approvare, rifiutare o revocare. L'approvazione è legata al checksum dello snapshot e l'accesso è ricontrollato per ogni lettura. Dashboard, CSV, Parquet e bundle FHIR R4 MeasureReport usano la stessa proiezione e producono un evento di audit. [FHIR MeasureReport R4](https://hl7.org/fhir/R4/measurereport.html)

La prima consultazione approvata fissa un solo snapshot distribuibile per versione del dataset. Se sorgente o archivio cambiano, dashboard ed export vengono bloccati finché la proiezione corrente non coincide con quella già distribuita. Nessun filtro per cohorti, sede o periodo personalizzato è disponibile. Questa regola impedisce di ottenere due conteggi diversi per lo stesso dataset da confrontare. Un'eventuale nuova versione distribuibile richiede una valutazione esplicita del rischio di differenze e incroci. La revoca blocca nuove letture di uno snapshot non più corrente anche prima del refresh.

Il collaudo non costituisce una certificazione di anonimato. Gli export già consegnati restano fuori dal controllo tecnico della piattaforma. Le integrazioni FHIR con sistemi terzi e la licenza dei cataloghi importati richiedono una verifica specifica.
