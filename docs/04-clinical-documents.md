# M3 — Documenti clinici, prima consegna

I documenti appartengono al paziente e al suo tenant. Un professionista verificato con accesso diretto può caricare un documento. L'autore può aggiungere versioni o archiviare il documento finché conserva l'accesso. Le note psicologiche sono visibili soltanto all'autore con accesso diretto. Le altre categorie sono visibili anche tramite grant di cartella clinica con consenso attivo. Per i binari serve il permesso download. I grant item di M2 riguardano l'anagrafica.

Configurare in .env.dev CLINICAL_CLAMAV_HOST con un clamd privato raggiungibile sulla porta 3310. Il limite INSTREAM deve permettere almeno 10 MiB. Impostare CLINICAL_MASTER_KEY con una chiave Fernet dedicata generata localmente e custodita separatamente dalle copie del database. Un errore del servizio o una scansione senza esito positivo bloccano l'upload. Django può usare file temporanei prima della scansione, quindi il volume temporaneo del backend va protetto e reso effimero. Usare solo dati sintetici in locale.

Eseguire make dev per ricostruire e applicare le migrazioni. Usare una sessione autenticata con CSRF per i metodi di scrittura.

- GET /api/v1/clinical/patients/{patient}/documents/ elenca le versioni correnti visibili. Il parametro q filtra il titolo.
- POST sullo stesso percorso accetta multipart con file, title e kind facoltativo. Valori di kind sono report, nutrition, psychology e other.
- GET /api/v1/clinical/documents/{document}/ elenca lo storico visibile. POST aggiunge una versione. DELETE archivia tutte le versioni mantenendo i dati cifrati.
- GET /api/v1/clinical/versions/{version}/download/ richiede autorizzazione al momento della richiesta.
- GET /api/v1/fhir/metadata dichiara le letture disponibili. DocumentReference e Patient sono leggibili per identificativo sui rispettivi percorsi FHIR. Il riferimento Patient è omesso se il destinatario non ha accesso diretto all'anagrafica.

La validazione confronta il tipo dichiarato con le firme iniziali di PDF, PNG, JPEG e DICOM con preambolo. I file sono consegnati come allegati. Firma e scansione non sostituiscono la validazione strutturale di ciascun formato. Il titolo rimane nei metadati relazionali per la ricerca. Usare titoli generici.

Il test d'integrazione usa contenuti sintetici e sostituisce il solo verdetto dello scanner durante il flusso positivo. Verifica anche l'assenza di configurazione dello scanner, l'isolamento, l'archiviazione e la revoca. Vedere le limitazioni aperte prima dell'uso operativo.
