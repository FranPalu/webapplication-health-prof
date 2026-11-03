# RUOLO
Sei un principal engineer senior, architetto software, esperto di sicurezza e responsabile di prodotto attento agli aspetti normativi. Lavorerai in autonomia nella repository esistente [PERCORSO/URL REPO], estendendola fino a farla diventare una piattaforma completa di collaborazione in ambito sanitario. Io non scriverò codice: devi pianificare, implementare, testare, documentare e correggere tutto da solo.

# REGOLE DI LAVORO (OBBLIGATORIE)
1. PRIMA: analizza la repo (stack, struttura, dipendenze, test, CI, convenzioni) e scrivi /docs/00-repo-audit.md. Riusa lo stack e le convenzioni esistenti dove sensato; giustifica ogni cambiamento in /docs/adr/ (Architecture Decision Records).
2. POI: scrivi /docs/01-architecture.md e /docs/02-roadmap.md suddividendo il lavoro in milestone (M0..M9 qui sotto). NON tentare di fare tutto in un solo passaggio.
3. Implementa una milestone alla volta. Per ciascuna: codice, migrazioni, test unitari e di integrazione, documentazione e breve voce di CHANGELOG. Esegui linter, type check e test; correggi tutti i fallimenti prima di proseguire. Usa Conventional Commits, commit piccoli e atomici.
4. Non lasciare mai stub TODO, endpoint finti o logica segnaposto senza segnalarli in /docs/KNOWN_LIMITATIONS.md. Non inventare mai credenziali: usa .env.example e documenta ogni variabile.
5. Fornisci docker-compose per lo sviluppo locale (app, DB, object storage, coda, mail catcher), dati di seed con SOLO pazienti sintetici FITTIZI e un setup a comando unico (`make dev`).
6. Al termine di ogni milestone stampa: cosa è stato fatto, come eseguirlo, come testarlo, problemi aperti e milestone successiva.
7. Se un requisito è ambiguo, scegli l'opzione più sicura e semplice, registrala in un ADR e prosegui.

# OBIETTIVO DEL PRODOTTO
Piattaforma web multi-tenant (responsive, PWA-ready) per professionisti sanitari (nutrizionisti, medici, psicologi, altri), ospedali e cliniche pubblici/privati, farmacie e pazienti. L'italiano è la lingua predefinita, l'inglese secondaria (i18n fin dal primo giorno). Mercato target: Italia/UE.

# REQUISITI FUNZIONALI

## M1 – Identità, tenancy, RBAC
- Entità: Organizzazione (ospedale, clinica, studio, farmacia), Professionista, Paziente, Ricercatore, Admin. Un Professionista può appartenere a più Organizzazioni; un Paziente può essere collegato a più Professionisti/Organizzazioni.
- Flussi di registrazione e onboarding per ruolo; workflow di verifica dei professionisti (caricamento numero di iscrizione all'albo/licenza, approvazione manuale da parte dell'admin; prevedi un'interfaccia pluggable per controlli su registri ufficiali).
- Autenticazione: email+password con hashing robusto (argon2), MFA (TOTP) obbligatoria per professionisti e admin, predisposizione OAuth/OIDC, integrazione SPID/CIE come interfaccia adapter con documentazione.
- RBAC + controlli basati su attributi (ruolo, organizzazione, relazione con il paziente). Negazione per impostazione predefinita.

## M2 – Motore di consenso e condivisione (funzione centrale)
- Modello generico "Share": qualsiasi documento/risorsa può essere condiviso tra qualsiasi coppia di attori: professionista↔professionista, professionista↔paziente, paziente↔struttura, struttura↔struttura.
- Ogni condivisione ha: concedente, destinatario, ambito (singolo elemento / cartella / intera cartella clinica), permessi (visualizza, scarica, commenta, ri-condividi), finalità, scadenza, revoca e una voce di audit immutabile.
- Consenso del paziente esplicito, granulare e revocabile (GDPR art. 9), testi di consenso versionati, storico dei consensi e dashboard "chi ha avuto accesso ai miei dati".
- Accesso di emergenza "break-glass" con motivazione obbligatoria e audit rafforzato.
- Messaggistica sicura e commenti collegati agli elementi condivisi; notifiche (email + in-app).

## M3 – Documenti e dati clinici
- Upload/archiviazione di PDF, immagini, immagini tipo DICOM, referti di laboratorio, piani alimentari, note psicologiche (con visibilità extra-ristretta). Object storage cifrato (chiavi per tenant, envelope encryption), hook antivirus, validazione del tipo di file, limiti di dimensione, versioning, soft delete con politiche di retention.
- Dati strutturati dove possibile: usa risorse HL7 FHIR (Patient, Practitioner, Organization, DiagnosticReport, Observation, DocumentReference, Consent) ed esponi una API di lettura compatibile FHIR.
- Ricerca full-text limitata dai permessi.

## M4 – Analisi preliminare assistita da AI (human-in-the-loop)
- Interfaccia "analysis provider" pluggable con queste implementazioni: (a) pipeline testo/referti di laboratorio: OCR (es. Tesseract o OCR cloud dietro adapter) → estrazione di analiti/valori/unità/intervalli di riferimento → segnalazione rule-based dei valori fuori range + riepilogo in linguaggio semplice generato da LLM; (b) pipeline imaging: adapter per modelli open pre-addestrati (es. Hugging Face / MONAI / TorchXRayVision) eseguiti in un worker containerizzato separato.
- Usa SOLO modelli pre-addestrati esistenti; non addestrare nulla. Documenta ogni modello: nome, licenza, uso previsto, limiti noti, versione fissata in una tabella model registry.
- Ogni output AI deve essere: etichettato "Analisi automatica preliminare – non è una diagnosi", salvato con nome/versione del modello, hash dell'input, timestamp e confidenza, NON visibile al paziente finché un professionista abilitato non lo ha revisionato (accetta / modifica / rifiuta), e il parere finale firmato deve essere archiviato separatamente dalla bozza AI.
- Non inviare mai dati identificabili a API AI di terze parti, salvo che l'Organizzazione lo abbia abilitato, sia impostato un flag DPA e i dati siano pseudonimizzati; di default usa modelli self-hosted.
- Harness di valutazione: set di test "golden" con dati sintetici/pubblici, test di regressione sull'accuratezza dell'estrazione e tabella di monitoraggio dei tassi di modifica/rifiuto da parte dei revisori.

## M5 – Pagamenti
- Integra Stripe (Stripe Connect per payout in stile marketplace a professionisti/strutture) dietro un'interfaccia PaymentProvider; supporta pagamenti una tantum di visite/esami, fatture/ricevute, rimborsi, webhook con verifica della firma e idempotenza.
- Non memorizzare mai dati di carta. Gestisci SCA/3-D Secure. Listini per organizzazione/servizio. Export per la fatturazione elettronica italiana (struttura i dati per l'invio a un provider SDI; implementa solo l'interfaccia adapter).
- Configurazione di tasse/commissioni e impostazione della commissione di piattaforma.

## M6 – Prenotazioni e prenotazione farmaci in farmacia
- Calendario e disponibilità per professionisti e strutture; prenotazione di visite ed esami di laboratorio/diagnostici; promemoria (adapter email/SMS); regole di cancellazione/riprogrammazione; pagamento alla prenotazione o in loco.
- Modulo farmacie: le farmacie aderiscono come Organizzazioni, pubblicano catalogo/disponibilità (import CSV + API); i pazienti possono PRENOTARE (non acquistare farmaci con obbligo di prescrizione senza un riferimento di ricetta valido). Gli articoli soggetti a prescrizione richiedono una ricetta caricata/collegata (supporta il numero di ricetta elettronica come campo; l'integrazione con i sistemi ufficiali è solo un'interfaccia adapter). La farmacia conferma/rifiuta e il paziente viene notificato.
- Ricerca geografica di strutture/farmacie vicine (PostGIS se lo stack lo consente).

## M7 – Livello dati per la ricerca
- Archivio analitico separato (es. schema/warehouse dedicato) alimentato da una pipeline ETL/ELT con job idempotenti e versionati.
- Includi solo record con consenso esplicito alla ricerca. De-identificazione: rimozione degli identificatori diretti, pseudonimizzazione con hashing a chiave, generalizzazione di date/luoghi, controlli di k-anonymity, soppressione delle celle piccole; documenta il metodo in /docs/research-anonymization.md.
- Catalogo dati + dizionario dei dati, controlli di qualità (completezza, validità, duplicati), normalizzazione terminologica (mappature LOINC, SNOMED CT, ICD-10 come tabelle di lookup), versionamento dei dataset, export in CSV/Parquet/bundle FHIR, accesso per Organizzazioni di Ricerca approvate tramite workflow di richiesta e approvazione con logging.
- Dashboard aggregate (conteggi, distribuzioni, trend) per i ricercatori.

## M8 – UX/UI
- Design system semplice, moderno, accessibile (WCAG 2.2 AA): layout pulito, spazi generosi, componenti coerenti, modalità chiara/scura, mobile-first, stati vuoto/errore/caricamento chiari. Dashboard specifiche per ruolo (paziente, professionista, admin di organizzazione, farmacia, ricercatore, admin di piattaforma).
- Produci un breve /docs/design-system.md e usa i design token.

## M9 – Hardening e rilascio
- Sicurezza: checklist OWASP ASVS L2, threat model (STRIDE) in /docs/security/, rate limiting, protezioni CSRF/XSS/SSRF, header di sicurezza, scansione di dipendenze e segreti in CI, SAST, logging strutturato senza PHI, backup e test di restore, audit log immutabile (hash-chained).
- Privacy: funzioni GDPR – export dei dati (portabilità), workflow di cancellazione/anonimizzazione nel rispetto dei obblighi di conservazione, template DPIA, template del registro dei trattamenti, runbook per data breach. Configurazione di residenza dei dati in UE.
- Osservabilità: health check, metriche, tracing, error tracking.
- Qualità: copertura test ≥80% sui moduli core, test E2E (Playwright) per i flussi critici (registrazione, condivisione, revisione AI, pagamento, prenotazione), script di load test.
- Pipeline CI/CD, Dockerfile, manifest di produzione Kubernetes o compose, scheletro IaC, note di rilascio, guide utente per ruolo, documentazione OpenAPI.

# VINCOLI NORMATIVI (da riflettere nel codice E nei documenti)
- Tratta tutti i dati sanitari come categorie particolari di dati ai sensi del GDPR; applica privacy by design e by default, minimizzazione dei dati, limitazione della finalità.
- Le funzioni AI possono qualificarsi come software dispositivo medico (MDR UE) e come AI ad alto rischio (AI Act UE). Pertanto: presenta gli output rigorosamente come supporto decisionale che richiede la validazione di un professionista, includi un disclaimer, mantieni piena tracciabilità e produci /docs/compliance/regulatory-notes.md con ciò che va fatto (revisione legale, DPIA, qualificazione MDR, marcatura CE se applicabile, indicazioni del Garante Privacy, interoperabilità AgID/FSE, considerazioni ISO 27001/13485/62304). Non dichiarare conformità: indica cosa è implementato e cosa resta da fare.
- Non fornire diagnosi mediche né decisioni terapeutiche in modo autonomo.

# REQUISITI NON FUNZIONALI
- Architettura modulare pulita (monolite modulare con confini chiari, worker per AI/ETL), API-first (OpenAPI), codice tipizzato, migrazioni, feature flag, configurazione via variabili d'ambiente, nessun segreto hardcoded.
- Obiettivi di performance: p95 API < 500 ms sugli endpoint principali; elaborazione asincrona per i task pesanti.

# DELIVERABLE
Codice funzionante, test, migrazioni, dati di seed, docker-compose, configurazione CI e tutti i documenti elencati sopra, più /README.md con istruzioni di setup e uno script demo che copra i flussi end-to-end.

# INIZIA ORA
Esegui solo il passo 1 (audit della repo) e il passo 2 (architettura + roadmap). Mostrami il riepilogo e il piano delle milestone proposto, poi attendi il mio "GO M1" prima di implementare ciascuna milestone.