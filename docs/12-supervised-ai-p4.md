# P4 · Workflow AI supervisionato

Il codice estende il collaudo sintetico, disabilitato per default e indisponibile fuori DEBUG. P4 resta **parziale rispetto ai requisiti clinici e produttivi**: implementazione dei controlli non equivale a validazione clinica o conformità. [ADR](adr/0016-p4-model-approval-source-and-signature.md), [prove](p4/verification.md), [tracciabilità](p4/traceability.md).

## Esecuzione locale

Seguire il setup di [M4](05-supervised-analysis.md). Servono `.env.dev` generato da `make env` e il peso Qwen verificato in `.analysis-models/qwen.gguf`.

```sh
CLINICAL_ANALYSIS_ENABLED=1 docker compose --env-file .env.dev --profile analysis up -d --build
```

Nel portale autenticato un professionista verificato con MFA e membership amministrativa apre Documenti clinici → Analisi preliminare → Registro modelli e controllo di esecuzione. Legge le schede e registra un'approvazione motivata per il solo collaudo sintetico. La revisione clinica reale delle schede è ancora richiesta. Un normale professionista può analizzare soltanto dopo l'approvazione e con relazione di cura attiva. Le condivisioni non abilitano analisi. Avvio e lettura dei job rifiutano pazienti sotto i 18 anni; i casi urgenti restano esclusi dall’uso previsto e il sistema non offre triage.

Aprire l'analisi registra l'inizio della revisione. Il flusso è queued → running → ready → in_review → accepted/modified/rejected; firma e pubblicazione sono eventi separati. Per accept/modify occorre confrontare tutti i valori con l'originale e confermare singolarmente le righe richieste. Le note di rifiuto e le segnalazioni sono cifrate. Una fonte incompleta non può essere attestata: occorre rifiutare e caricare una fonte leggibile. Nessun intervallo assente viene dedotto.

Le schede sono in `backend/identity/model_cards/registry.json`; la risposta API aggiunge l'hash del codice. La soglia OCR ingegneristica è 85/100, non validata clinicamente. Tutte le mappature terminologiche richiedono verifica del campione e del metodo. Le coordinate PDF sono punti dall'angolo alto sinistro; quelle OCR sono pixel dell'immagine analizzata, eventualmente rasterizzata, e non pixel del PDF. Il testo esatto della riga è sempre conservato. L'originale è aperto tramite download autorizzato in un URL locale del browser.

## Firma e pubblicazione

`CLINICAL_SIGNATURE_VERIFIER` indica una classe del deployment con metodo `verify(artifact, expected_digest, expected_signer_id)`. Il contratto è in `analysis_signing.py`. Il valore vuoto è il default sicuro e restituisce 503 alla verifica. Non esiste un provider reale integrato né una firma qualificata dimostrata.

Scaricare il contenuto da firmare dopo la revisione: JSON canonico UTF-8, senza BOM, senza newline finale, chiavi ordinate e separatori compatti, hash mostrato nel portale. Per CAdES il contenuto sottoscritto deve corrispondere esattamente a quei byte. Per PAdES il verificatore deve controllare anche il manifest incorporato e la corrispondenza con il documento visualizzato. Deve verificare certificato, revoca al momento della firma, eventuale timestamp, identità del professionista e binding del digest; errori di contenuto devono sollevare `InvalidClinicalSignature`, indisponibilità `SignatureUnavailable`. Non basta leggere un digest dichiarato dall'utente.

L'artefatto è limitato a 48.000 byte nell'interfaccia e al limite JSON nell'API; documenti firmati più grandi richiedono estensione controllata del trasporto. Il provider deve restituire `VerifiedClinicalSignature`; l'API verifica nuovamente autore, digest, formato, data non futura e autorizzazione. Identificativo e data di nascita sono richiesti prima della firma. La prova cifrata è append-only e cancellabile soltanto dal purge del documento sorgente. Conservazione a norma e validazione del provider restano aperte.

La pubblicazione richiede la prova di firma e il paziente collegato. Il paziente riceve esclusivamente il testo finale, mai la bozza o la motivazione del rifiuto. Una nuova decisione sul manifest o uno stop globale nasconde i vecchi esiti; riabilitare non li ripubblica. Questa scelta conservativa può nascondere anche opinioni già firmate: non usare il canale AI come unico archivio sanitario.

## API aggiunte

- `organizations/{id}/analysis/registry/`: GET schede e hash, POST enable/disable con hash corrente e motivo. Amministratore del tenant e professionista verificato; audit.
- `clinical/analysis/{id}/review-start/`: POST inizio immutabile della sessione per revisore. `review/` richiede sessione, confronto fonte e righe confermate.
- `clinical/analysis/{id}/incidents/`: POST categoria e nota cifrata; audit privo di nota clinica.
- `clinical/opinions/{id}/sign/`: POST artefatto base64 e identificatori dalla fonte. `publish/` senza firma verificata restituisce 409.
- `organizations/{id}/analysis/metrics/`: conteggi, tassi di modifica/rifiuto, tempo medio di revisione e righe estratte/incerte per versione. Lettura amministrativa con audit; nessun testo clinico.

Le metriche sono indicatori di processo. La durata inizia all'apertura, può includere inattività e non misura attenzione. Non esistono un rilevatore di drift clinicamente validato, un allarme automatico di degrado o un servizio completo di vigilanza; le segnalazioni richiedono presa in carico secondo CAPA. Nessun provider AI esterno è eseguibile in questo percorso. Il worker laboratorio usa una rete Compose interna che accede soltanto alle dipendenze necessarie. DB/storage/Redis sono anche connessi alla rete applicativa: questo non prova una segregazione di produzione o la sicurezza del nodo host.

## Imaging ed evidenze cliniche aperte

PyTorch/torchvision e strumenti del container sono stati aggiornati e scansionati. Il runner carica solo tensori con `weights_only=True`; la [conversione legacy](p4/imaging-preparation.md) è un processo separato, vincolato da hash, con eccezione SAST puntuale documentata. Il runner accetta una fixture autorizzata per hash, modalità chest_xray e vista AP/PA, rifiuta percorso esterno e input oltre i limiti. Rete disabilitata, filesystem read-only, capability rimosse. Output: punteggi grezzi ripetibili, `clinical_usable=false`, confidenza e localizzazione nulle. Metadati corretti non provano che l'immagine sia una radiografia in distribuzione. Non esiste un endpoint di analisi imaging per i pazienti.

Il report sintetico misura concordanza dell'estrazione, non sensibilità diagnostica. Con rotazione di 3° F1 scende a 0,80. Sensibilità, specificità, PPV, NPV, AUC, calibrazione, intervalli di confidenza clinici e analisi per età/sesso restano non stimabili senza dataset rappresentativo e protocollo approvato. Non sono stati inventati valori o popolazioni. Restano diritti dei pesi/dataset, validazione clinica, localizzazione, OOD clinico, fonte terminologica completa e licenziata, provider firma e conservazione, DPIA e valutazioni regolatorie. Il gate clinico resta bloccato.
