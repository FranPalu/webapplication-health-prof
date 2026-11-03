# Architettura della piattaforma sanitaria

Stato: progetto approvato per documentazione M0, 2026-11-03. Tutto ciò che segue
è architettura target, non descrizione di funzionalità già disponibili.

## Stack e confini

Django 5.2 LTS e Django REST Framework costituiscono il monolite modulare;
PostgreSQL/PostGIS il database operativo. React/TypeScript e componenti esistenti
restano il frontend, servito da Next.js su Node 24. Versioni patch, Python e
immagini saranno fissate nei lockfile in M1 dopo verifica di compatibilità.
La [pagina Django](https://www.djangoproject.com/download/) elenca 5.2 LTS tra
le serie supportate; non si assume che la patch rilevata oggi resti attuale.

Un reverse proxy espone un solo dominio: `/api/v1/` a Django, frontend a Next.
Il frontend non accede direttamente a database o bucket. La sessione è verificata
dal backend; nessun header di identità fornito dal browser è autorevole.
Il sorgente legacy resta utilizzabile separatamente durante la migrazione;
non sono consentiti percorsi legacy che aggirino le nuove policy.

Moduli Django e responsabilità:

- Identità e organizzazioni: account, profili, membership, verifica professionale.
- Pazienti e autorizzazioni: anagrafiche per tenant, relazioni di cura, policy.
- Consensi e condivisioni: testi versionati, decisioni del paziente e concessioni.
- Documenti e dati clinici: metadati, versioni, osservazioni e lettura FHIR.
- Comunicazioni: conversazioni autorizzate, notifiche e adapter dei canali.
- AI: job, provenienza, bozze, revisione e pareri finali separati.
- Pagamenti e prenotazioni: listini, transazioni, fatture, slot e farmacia.
- Ricerca: estrazione approvata e catalogo; database e credenziali separati.
- Audit: eventi di sicurezza e accesso, integrità e verifica dei checkpoint.

Ogni modulo espone servizi di dominio tipizzati; le viste API orchestrano
validazione e servizi senza duplicare le policy. Le operazioni atomiche usano
transazioni PostgreSQL; gli effetti esterni sono pubblicati tramite outbox.

## Identità, tenancy e autorizzazione

Account email/password con modello utente personalizzato dalla prima migrazione,
Argon2, verifica email, recupero account e sessioni server. Cookie HttpOnly,
Secure in produzione, SameSite e CSRF per le operazioni mutanti, incluso login.
TOTP obbligatorio per professionisti e amministratori: la sessione incompleta
accede solo al completamento dell'onboarding/MFA. Recovery code monouso protetti;
reset MFA tracciato e senza scorciatoie amministrative silenziose.

Un account può avere più profili e membership. Il cambio organizzazione verifica
la membership sul server. Il paziente può esistere senza account di accesso:
il collegamento a un account richiede una verifica, non un confronto automatico
del codice fiscale. Le schede cliniche restano separate per organizzazione.

Una richiesta autorizzata combina identità, stato professionale, ruolo, tenant,
relazione di cura, risorsa, finalità e concessione applicabile. Membership e ruolo
amministrativo non concedono automaticamente lettura clinica. Il paziente vede
solo risorse pubblicabili e collegate alla sua identità verificata.

Le policy filtrano queryset prima di paginazione, conteggi e ricerca; controllano
anche creazione, modifica, download e job. Le sole object permissions DRF non
filtrano automaticamente le liste: [riferimento ufficiale](https://www.django-rest-framework.org/api-guide/permissions/).
I grant fra organizzazioni sono eccezioni esplicite e limitate; non cambiano il
tenant proprietario né concedono accesso a tutte le sue risorse.

## Consenso, Share e audit

Un registro tipizzato delle risorse fornisce identificatore, tipo, tenant,
paziente e classificazione; evitare riferimenti generici senza verifica di esistenza
e proprietà. Share collega attori individuali o organizzativi a elemento,
cartella o fascicolo, con finalità, permessi, scadenza e stato di revoca.
La ri-condivisione non può ampliare diritti, durata o finalità del grant originario;
revocare un grant invalida i discendenti. Il consenso del paziente conserva testo,
versione, evidenza, ambito, finalità e storico. I booleani legacy non diventano
automaticamente nuovi consensi validi.

L'accesso è rivalutato al momento dell'uso, anche per job e download. Revoca e
scadenza impediscono accessi futuri; non promettono di recuperare file già scaricati.
Break-glass è disabilitato per default e richiede abilitazione organizzativa,
professionista verificato, motivazione, durata limitata, alert e revisione successiva.
Non abilita export massivi o ricerca.

Audit applicativo append-only con attore, tenant, azione, riferimento opaco,
esito, finalità, timestamp e correlazione, senza testo clinico. Catene per tenant
con serializzazione delle append concorrenti e checkpoint su storage immutabile
separato. Ruoli DB senza UPDATE/DELETE per l'applicazione; verifica periodica
della catena. Gli accessi clinici falliscono se non è possibile registrarli.
Una catena da sola non impedisce a un amministratore DB di riscriverne la storia.

## API e servizi asincroni

REST `/api/v1/`, OpenAPI generata e client TypeScript verificato in CI. Endpoint
per risorsa, paginazione e filtri server sostituiscono il download dell'intero
studio. Errori pubblici con codice stabile e request ID, senza dettagli interni.
FHIR R4 read-only in M3, con CapabilityStatement e supporto dichiarato per
Patient, Practitioner, Organization, DiagnosticReport, Observation,
DocumentReference e Consent; le stesse policy si applicano ai riferimenti FHIR.

Celery/Redis gestisce comunicazioni, scansioni, AI ed ETL con code e credenziali
separate. Messaggi contengono ID opachi, non documenti o segreti. Task idempotenti,
retry limitati, timeout e gestione dei fallimenti; riconciliazione degli esiti
incerti prima di ripetere pagamenti o invii. Ricontrollare permessi e consenso
prima dell'elaborazione e prima della pubblicazione del risultato.

Contratti adapter: identità OIDC/SPID/CIE, verifica albi, storage/KMS, antivirus,
OCR/AnalysisProvider, PaymentProvider, email/SMS, SDI e ricette ufficiali.
Un adapter non configurato restituisce indisponibilità esplicita; non simula
successo. I mock sono confinati ai test. Le specifiche concrete accompagnano
la milestone di competenza.

## Documenti, AI e ricerca

Upload in quarantena con limiti effettivi, tipo e contenuto validati, antivirus
fail-closed; soltanto versioni approvate sono leggibili. Bucket privati, envelope
encryption con chiave dati per oggetto e chiavi di protezione per tenant gestite
tramite KMS; rotazione e ripristino delle chiavi inclusi nei test di backup.
Download mediato dal backend per rivalutare revoca e permessi. Soft delete,
retention e blocchi di conservazione precedono la cancellazione fisica.

AI in worker isolati con modelli pre-addestrati fissati per versione e licenza.
Input e output tracciati tramite hash, modello, configurazione e timestamp;
confidenza con significato documentato, senza valori inventati se non disponibile.
Ogni bozza porta «Analisi automatica preliminare – non è una diagnosi».
Accetta/modifica/rifiuta produce un evento di revisione; il parere finale è un
artefatto distinto con revisore, attestazione e hash. Tale attestazione non viene
presentata come firma qualificata. Il paziente non vede bozze o output rifiutati.
Provider esterni richiedono abilitazione organizzativa, DPA registrato e
pseudonimizzazione verificata; default self-hosted e nessun training.

Ricerca in database separato, alimentato solo da job con consenso ricerca valido.
HMAC con chiave dedicata, generalizzazione e soppressione; soglie approvate per
dataset, controlli sulle query ripetute e export registrati. Pseudonimizzazione
e k-anonymity non sono una garanzia di anonimato. Revoca esclude nuovi export e
invalida le copie interne/dataset interessati secondo il workflow documentato;
gli export già consegnati richiedono tracciamento e gestione contrattuale.

## Migrazione e operatività

Import versionato e idempotente per `(sorgente, owner, tipo, id)` con manifest,
dry-run, report di scarti e riconciliazione. Mappatura owner→organizzazione
esplicita; nessun account o consenso dedotto dagli header legacy. M1 importa
anagrafiche; M3 documenti; M5 fatture; M6 appuntamenti e comunicazioni.
Le funzionalità non migrate restano solo nell'ambiente legacy isolato.

Prima del cutover completo: backup D1/R2 verificato, finestra di sola lettura,
import finale, verifica conteggi/hash e test dei flussi. Niente doppia scrittura.
Rollback prima di nuove scritture riporta al backup legacy; dopo nuove scritture
richiede riconciliazione esplicita, non il semplice riavvio del vecchio sistema.

M1 introduce Compose con frontend, backend, PostgreSQL/PostGIS, Redis, storage
S3 compatibile, worker e mail catcher; `make dev` prepara migrazioni e seed
sintetici idempotenti. Configurazione in env documentate, segreti locali generati
fuori Git, servizi non esposti pubblicamente. AI/ETL pesanti arrivano nelle loro milestone.

Produzione: residenza UE verificata per dati, backup, log e subprocessori;
metriche e tracing senza PHI. Obiettivo p95 <500 ms sulle API interattive misurato
con carico/dataset dichiarati; OCR, export e inferenza restituiscono job asincroni.
PWA senza cache clinica offline; i18n IT/EN e accessibilità da M1.

## Decisioni e limiti

Vedere [ADR](adr/README.md), [roadmap](02-roadmap.md) e
[limitazioni](KNOWN_LIMITATIONS.md). Nessuna migrazione, infrastruttura o API
descritta qui è stata creata in M0.
