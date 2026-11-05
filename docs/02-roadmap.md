# Roadmap M0–M9

Data: 2026-11-03. Una milestone alla volta. M0 è documentale; M1 richiede
«GO M1», poi ogni milestone richiede il relativo GO. Non sono stime temporali.

## Regole di completamento

Ogni milestone applicativa consegna codice funzionante, migrazioni, test unitari
e di integrazione, documentazione, env di esempio e CHANGELOG. Commit piccoli
Conventional Commits. Adapter non configurati disabilitati, limiti registrati.
Nessuna credenziale inventata, pazienti esclusivamente sintetici nei seed.

Gate: lint, typecheck, test e build verdi; migrazioni provate da database vuoto
e dalla versione precedente; OpenAPI/client allineati; copertura >=80% sui moduli
core introdotti. Ruff, mypy e pytest per Django; ESLint, TypeScript e test Node
per il frontend; Playwright aggiunto ai flussi via via disponibili. Test DB su
PostgreSQL, non solo SQLite. In M1 risolvere anche la baseline rossa legacy.

Ogni chiusura riporta cosa è stato fatto, comandi di avvio e test, problemi aperti
e milestone successiva. Sicurezza, i18n e accessibilità accompagnano ogni fase.

## M0 — Audit e progettazione

Consegna: [audit](00-repo-audit.md), [architettura](01-architecture.md), roadmap,
[ADR](adr/README.md), [limitazioni](KNOWN_LIMITATIONS.md), note normative iniziali
e collegamenti README. Nessuna implementazione applicativa o migrazione.

Accettazione: evidenze distinte da ipotesi, requisiti M1–M9 mappati, baseline dei
controlli esplicita, documenti coerenti e link locali validi. I difetti preesistenti
sono registrati e bloccano l'avanzamento tecnico finché corretti in M1.

## M1 — Fondazioni, identità e tenancy

Dipende da M0 e GO M1. Django/DRF, PostgreSQL/PostGIS, Next su Node, Compose,
`make dev`, seed sintetici, env documentate, CI e OpenAPI. Account personalizzato,
onboarding per ruolo, membership multiple, relazioni paziente, verifica manuale
professionisti e adapter registri; Argon2, TOTP, recovery, sessioni e CSRF.
Interfacce OIDC/SPID/CIE documentate e non operative senza configurazione.
Policy deny-by-default, audit di base, IT/EN e token UI iniziali.
Import dry-run/idempotente delle anagrafiche senza inferire consensi.

Accettazione: avvio da checkout pulito; registrazione/login/MFA/logout e recupero
testati; professionista non verificato bloccato; nessun accesso tramite header
falsi, ID altrui, cambio tenant o ruoli autoassegnati. Liste e dettagli applicano
la stessa policy. I test esistenti tornano verdi. Nessuna funzione clinica futura
è abilitata solo perché l'utente ha completato il login.

## M2 — Consenso, Share e collaborazione

Dipende da M1. Registro risorse condivisibili (incluse cartelle e anagrafiche),
attori individuali/organizzativi, Share con permessi/finalità/scadenza/revoca,
consensi versionati, dashboard accessi, emergenza controllata, messaggi e commenti,
email senza contenuto clinico e notifiche in-app. Audit hash-chained, checkpoint
esterni e permessi append-only. M3 estende il registro ai documenti binari.

Consegna in corso: modelli e API su anagrafica paziente, destinatario professionista
singolo o organizzazione, consenso esplicito versionato, messaggi append-only,
notifiche generiche, storico accessi, break-glass di 15 minuti e comando per
verificare l'hash-chain. Limiti espliciti in [docs M2](03-sharing-consent.md).

Accettazione prima della chiusura: test delle coppie di attori supportate, grant
scaduti/revocati, revoca dei discendenti, nessun aumento privilegi nella
ri-condivisione; accessi e break-glass registrati; test PostgreSQL, CI, OpenAPI,
lint e typecheck verdi. Checkpoint esterni, risorse documentali e cartelle
gerarchiche restano limitazioni dichiarate e non sono requisito di completamento
di M2.

## M3 — Documenti e interoperabilità

Implementata e verificata in ambiente locale. Le prove usano dati sintetici,
ClamAV e SeaweedFS. Le attivazioni AWS KMS e R2 dipendono dalle credenziali
del destinatario. Vedere [guida M3](04-clinical-documents.md).

Dipende da M2. PDF, immagini e DICOM, note psicologiche ristrette, quarantena,
antivirus, envelope encryption/KMS, limiti, versionamento, retention e ricerca.
Import R2 con hash e riconciliazione. Dati strutturati e API FHIR R4 di lettura
per le sette risorse richieste, supporto dichiarato nel CapabilityStatement.

Accettazione: file camuffati, sovradimensionati o non scansionati non leggibili;
tenant e note riservate isolati; revoca impedisce nuovi download; rotazione chiavi
e restore verificati; ricerca e riferimenti FHIR non rivelano risorse negate.

## M4 — AI preliminare supervisionata

Implementata per collaudo locale su dati sintetici. Vedere [guida M4](05-supervised-analysis.md) e [report di collaudo](05-m4-validation.md).

Dipende da M3. OCR→analiti/valori/unità/range→regole→riepilogo LLM; pipeline
imaging in worker isolato. Solo modelli pre-addestrati con licenza, versione,
uso previsto e limiti nel model registry. Provenienza completa, disclaimer,
bozza separata dal parere finale attestato, revisione accetta/modifica/rifiuta.
Golden set sintetico/pubblico ed esiti di modifica/rifiuto monitorati.

Accettazione: paziente escluso da bozze e rifiuti anche via URL/API; revisore
autorizzato; revoca durante il job gestita; nessun invio esterno senza tutti i
prerequisiti; metriche di estrazione e soglie del golden set fissate prima del
rilascio del modello. Un disclaimer non costituisce qualificazione regolatoria.

## M5 — Pagamenti e documenti contabili

Avviata con listini, ordini e rimborsi in simulazione interna. Vedere [prima consegna M5](06-payments-sandbox.md).

Dipende da M3 e dall'avanzamento sequenziale dopo M4. PaymentProvider Stripe e
Connect, SCA/3DS, listini, commissioni, imposte configurabili, rimborsi, fatture
e ricevute, webhook firmati e idempotenti. Import fatture preservando snapshot,
stato e numerazione. SDI solo adapter; nessun dato carta nel sistema.

Accettazione: sandbox Stripe per successo/fallimento/SCA, replay e ordine inverso
dei webhook, rimborsi e riconciliazione; nessuna doppia contabilizzazione. I
valori ENPAB legacy non si applicano a professioni/regimi diversi per default.

## M6 — Prenotazioni e farmacia

Prenotazioni, farmacia, portale, import e ricerca geografica disponibili. SMS e verifica ufficiale NRE richiedono adapter. Vedere [guida M6](07-bookings-pharmacy.md).

Dipende da M5. Disponibilità per professionista/struttura, visite/esami,
pagamento anticipato o in loco, cancellazioni, riprogrammazione, email/SMS.
Migrazione agenda/reminder. Farmacie come organizzazioni, cataloghi CSV/API,
disponibilità, prenotazione con ricetta collegata/NRE e conferma/rifiuto.
Adapter sistemi ricette ufficiali non simulato; ricerca PostGIS.

Accettazione: contesa sullo stesso slot/stock, cambio ora Europe/Rome, cancellazioni
e rimborsi coerenti, reminder idempotenti, import CSV con report errori. Farmaci
soggetti a prescrizione non confermabili senza verifica del riferimento;
presenza o formato NRE non equivalgono a validazione ufficiale.

## M7 — Ricerca

Dipende da M2/M3 e dall'avanzamento sequenziale dopo M6. Database separato,
ETL versionato/idempotente, consenso ricerca, HMAC/generalizzazione/k-anonymity/
soppressione; catalogo, dizionario, qualità, lookup LOINC/SNOMED CT/ICD-10 con
licenze e provenienza, dataset versionati, CSV/Parquet/bundle FHIR e aggregati.
Workflow richieste e approvazione organizzazioni di ricerca.

Accettazione: esclusione consensi assenti/revocati, replay ETL senza duplicati,
assenza identificatori diretti, soppressione celle piccole e rischio da query
combinate; export autorizzati tracciati e revoca propagata ai dataset interni.
Consegna `research-anonymization.md`; non dichiarare anonimi i dati pseudonimi.

## M8 — UX/UI completa

Dipende da M1–M7. Dashboard paziente, professionista, amministratore organizzativo,
farmacia, ricercatore e amministratore piattaforma. Design system documentato,
token, IT/EN, chiaro/scuro, mobile-first, stati vuoto/errore/caricamento e PWA.

Accettazione: flussi a tastiera e screen reader, contrasto, focus, errori form,
responsive e traduzioni verificati; nessuna cache offline di PHI. Verifica WCAG
2.2 AA con controlli automatici e manuali, non soltanto uno score automatico.

## M9 — Hardening e rilascio

Dipende da tutte le precedenti. Checklist ASVS L2, STRIDE, CSRF/XSS/SSRF,
rate limit/header, SAST, scansione dipendenze/segreti, backup e restore,
health/metriche/tracing/error tracking senza PHI. Portabilità, cancellazione e
conservazione, template DPIA/registro trattamenti e runbook data breach.
Residenza UE, Dockerfile e Compose produzione, scheletro IaC, CI/CD, OpenAPI,
guide per ruolo, release notes e script demo completo.

Accettazione: restore completo inclusi chiavi e audit, E2E registrazione→Share→
revisione AI→pagamento→prenotazione, copertura core >=80%, load test riproducibile
con p95 API principali <500 ms su ambiente/carico dichiarati. Rischi e verifiche
regolatorie aperti devono essere espliciti; il rilascio tecnico non autorizza
automaticamente l'uso clinico o la messa sul mercato come dispositivo medico.
