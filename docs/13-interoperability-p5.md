# P5 · Interoperabilità supervisionata

P5 è implementata nel perimetro tecnico sintetico descritto qui. Rimane **parziale rispetto a interoperabilità nazionale, profili italiani/IPS, OAuth reale accreditato e uso clinico**. Tutti i nuovi ingressi richiedono `DJANGO_DEBUG=true` e `FHIR_INTEROP_ENABLED=1`; le letture preesistenti conservano le proprie autorizzazioni. Non dichiariamo conformità FHIR completa, SMART, EHDS o accreditamento FSE. [ADR](adr/0017-p5-supervised-interoperability.md) · [tracciabilità](p5/traceability.md) · [esiti](p5/verification.md).

## Avvio locale

`make env` genera anche credenziali locali PACS casuali in `.env.dev`, senza stamparle e senza ruotare quelle esistenti. Non copiarle in documenti, URL o repository.

```sh
make env
FHIR_INTEROP_ENABLED=1 docker compose --env-file .env.dev --profile pacs up -d --build
```

Portale: `http://localhost:8080`; visualizzatore sintetico: `http://localhost:8090/viewer?StudyInstanceUIDs=UID_RITORNATO_DALL_API`. Occorre essere autenticati con MFA nel portale usando lo stesso hostname; il cookie non passa da `localhost` a `127.0.0.1`. La vista richiede uno studio già mappato e autorizzato. Orthanc non pubblica porte sull'host e non accetta DIMSE. Il visualizzatore statico può aprirsi senza sessione, ma il recupero dei dati viene negato.

Per l'importazione configurare `PACS_ASSIGNING_AUTHORITY` e, per HL7, `HL7_ASSIGNING_AUTHORITY` e `HL7_SENDING_APPLICATION` con valori del mittente approvato. I test usano valori esplicitamente sintetici, non riferimenti a enti reali. Per disabilitare i flussi nuovi riavviare senza il flag; fermare anche il profilo `pacs` quando non serve.

## FHIR R4

Base `/api/v1/fhir`. Ricerca GET per Patient, Organization, Practitioner, Consent, DocumentReference, Encounter, DiagnosticReport, Observation, Provenance e ServiceRequest (quest'ultimo solo se P3 è abilitata). Parametri ammessi: `_id`, `_count` 1–100, `_offset` 0–10000, `patient` e `code` dove dichiarati. Ritorna Bundle `searchset`, totale già filtrato e link di pagina. Parametri duplicati, `_include`, chaining e ricerche non implementate sono rifiutati. `_offset` è un parametro locale documentato, non una pretesa di ricerca FHIR universale.

I metodi di lettura riutilizzano le policy esistenti: nessuna espansione di accesso a note psicologiche, referti preliminari o pazienti estranei. Ogni risorsa restituita e ogni ricerca hanno audit. Binary è leggibile solo attraverso un DocumentReference con download autorizzato; gli URL dei documenti puntano a questo percorso quando P5 è attiva. Non sono ammessi scope Binary autonomi.

POST DiagnosticReport e PUT DiagnosticReport/{id} supportano soltanto un referto **preliminary**, codice di laboratorio e osservazioni contenute ammesse dal profilo locale. Le osservazioni sono nuove versioni immutabili. La conferma indipendente del paziente usa l'estensione `urn:claria:fhir:patient-source-confirmation-v1` con `identifier_kind`, `identifier_value`, `source_birth_date`; l'aggiornamento richiede inoltre `urn:claria:fhir:correction-reason-v1` e `If-Match: W/"VERSIONE"`. Esempi verificati sono nel [bundle sintetico](p5/evidence/fhir-synthetic.json). Una risposta 201/200 non è una firma clinica: il paziente non riceve il preliminare. Scrittura di altri tipi, transazioni generiche, conditional create e upsert non sono implementati. I nuovi ingressi rifiutano minori; rappresentanza e urgenze restano escluse dall'uso previsto.

Il CapabilityStatement riflette le funzionalità abilitate. La correzione del consenso aggiunge il riferimento al testo/policy versionato richiesto dall'invariante R4 `ppc-1`; non trasforma il testo seed in un consenso legalmente approvato. [FHIR REST](https://hl7.org/fhir/R4/http.html), [ricerca](https://hl7.org/fhir/R4/search.html), [Consent](https://hl7.org/fhir/R4/consent-definitions.html).

## OAuth/SMART delegato

Non esiste un authorization server locale. Configurare un provider di fiducia con HTTPS, PKCE S256, verifiche state/redirect proprie del provider e introspezione RFC 7662. Impostazioni: `SMART_ISSUER`, `SMART_AUTHORIZATION_URL`, `SMART_TOKEN_URL`, `SMART_INTROSPECTION_URL`, `SMART_CLIENT_ID`, `SMART_CLIENT_SECRET`. Senza configurazione non viene accettato alcun bearer. Non seguire redirect o inviare token a URL forniti dall'utente.

Il provider deve produrre claim verificati: `active=true`, `iss`, `aud` uguale alla base FHIR, `exp`, `sub` mappato all'UUID interno, `auth_version`, `client_id` e `scope`. Il flusso paziente richiede anche `tenant`, `patient`, `grant_id`. Non effettuiamo account linking automatico da email/CF. Il flusso di ricerca richiede `research_access_request`, tenant, `user/MeasureReport.rs`, `amr` contenente `mfa` e `auth_time` entro un'ora. Gli header errati non ripiegano sulla sessione.

L'amministratore del tenant con MFA registra l'applicazione in `organizations/{id}/interop/applications/`; il paziente proprietario concede ambiti espliciti con scadenza massima 90 giorni in `clinical/patients/{id}/interop/grants/`. Revoca di applicazione o grant è append-only e ricontrollata ad ogni chiamata, insieme a membership e versione dell'account. Scope paziente ammessi: `.r`, `.s`, `.rs` solo sui tipi dichiarati, senza wildcard o privilegi di scrittura. Il grant è un'autorizzazione tecnica: testi, DPA e basi giuridiche richiedono P6 e validazione legale. [SMART App Launch](https://www.hl7.org/fhir/smart-app-launch/conformance.html).

Le prove simulano soltanto la risposta del provider. Non abbiamo eseguito login OAuth/PKCE con un IdP reale, accreditato SPID/CIE o una certificazione SMART. L'introspezione ad ogni chiamata privilegia la revoca rispetto alla cache e richiede misure di latenza/disponibilità prima dell'uso reale.

## HL7 v2

POST `interop/patients/{id}/hl7/` con `message` accetta messaggi CR-delimitati v2.5.1, processing ID `T`, ACK enhanced `AL/AL`, sender e authority configurati. Profili: ADT^A01, ORM^O01, ORU^R01. PID deve fornire un identificativo MR univoco con authority e data di nascita completa. L'accesso richiede professionista verificato, MFA e relazione di cura su maggiorenne.

Il messaggio e la proposta sono cifrati. Il controllo di idempotenza è per mittente/tenant/control ID e impronta dell'input; stesso ID con contenuto diverso restituisce 409. Risposta 202 e `MSA|CA` significano soltanto commit in quarantena. GET `interop/hl7-receipts/{id}/` permette al curante autorizzato di leggere fonte e proposta con audit. Non vengono creati automaticamente episodi, ordini o referti e non viene notificata una presa in carico clinica. La revisione umana deve passare dalle normali API cliniche.

Messaggi con segmenti, unità, stati, limiti di riferimento, flag o tipi di dato non mappati vengono rifiutati; correggere la mappatura con il mittente o gestire manualmente. Non accettiamo correzioni/cancellazioni non riconciliate. Il motore implementato è un ingresso HTTP supervisionato con quarantena, non un engine ospedaliero completo: MLLP/mTLS macchina, routing continuo, riconciliazione e collaudo LIS/RIS/HIS restano aperti. Non è installato un Mirth/NextGen con licenza presunta.

## PACS e OHIF

POST `interop/patients/{id}/pacs/` riferisce una versione DICOM già archiviata con `version` e i tre campi di identificazione. PatientID, PatientBirthDate e IssuerOfPatientID nel file devono coincidere. Profilo limitato: CR/DX/Secondary Capture, una istanza per studio, un frame, scala di grigi, little endian non compresso, dimensioni e pixel coerenti. CT/MR, multiframe, compressi, strutture e tag inattesi sono rifiutati; nessuna conversione di orientamento o valori clinici.

Il derivato conserva pixel e attributi geometrici ammessi, rimuove tag privati e identificatori, rimappa gli UID per namespace paziente/tenant. Le VR devono corrispondere al dizionario; non sono ammesse sequenze che nascondano dati in tag altrimenti consentiti. Non vengono rilevate scritte nei pixel: BurnedInAnnotation=NO è una dichiarazione della fonte, non una prova. Il risultato è **pseudonimizzato, non dimostrato anonimo**.

STOW avviene solo dietro l'ingresso autorizzato. QIDO e WADO passano da `dicom-web/studies`, richiedono UID mappati e verificano contesto e permessi correnti. Non esistono listing indiscriminato, URL upstream scelto dal client o proxy di percorsi arbitrari. Metadati identificativi/BulkDataURI non sono esposti; pixel accessibili soltanto per l'istanza mappata. OHIF usa lo stesso gateway, upload disattivato e isolamento necessario al rendering. [Sicurezza Orthanc](https://orthanc.uclouvain.be/book/faq/security.html), [DICOMweb](https://orthanc.uclouvain.be/book/plugins/dicomweb.html), [OHIF](https://docs.ohif.org/configuration/datasources/dicom-web/).

La radice Orthanc è read-only e il solo plugin DICOMweb viene caricato da percorso immutabile; configurazione con segreti soltanto in tmpfs e storage in volume dedicato. OHIF e base Orthanc sono fissati per digest. TLS/mTLS, storage cifrato PACS, retention del derivato, backup/restore, least privilege di tutti i container, scansione OS e validazione diagnostica restano prerequisiti produttivi. L'immagine non è un modello AI e non abilita l'imaging P4 per pazienti.

## Ricerca asincrona

GET `fhir/$export?_type=MeasureReport&access_request=UUID`, header `Prefer: respond-async`, avvia un job con scadenza un'ora. Polling all'URL Content-Location, manifest e download NDJSON richiedono sessione amministrativa di ricerca o bearer specifico con MFA recente. Il worker verifica nuovamente account, membership, richiesta approvata e snapshot. Consensi/digest sono ricontrollati anche prima di consegnare il file. Il reconciler riprende i job ancora in coda.

Si esporta soltanto la proiezione aggregata fissa M7, con soglia di celle già prevista, non risorse Patient né righe individuali. `_since`, gruppi e tipi clinici generici non sono implementati. I test coprono pipeline e revoche con confine di archivio simulato dichiarato; la suite completa prova separatamente l'archivio reale su DB dedicato. Governance, attacchi differenziali e valutazione di anonimato restano P6.

## Integrazioni nazionali e EHDS

[Contratti nazionali e gap FSE](p5/national-integrations.md) · [EHDS](compliance/ehds-assessment.md). Nessun adapter reale nazionale è configurato o viene contattato dai flussi nuovi. I mock servono a verificare contesto, idempotenza e binding della ricevuta; non dimostrano accreditamento, ricetta valida, pagamento, invio TS/SDI o identità SPID/CIE.
