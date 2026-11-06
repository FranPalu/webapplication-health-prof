# Cartella clinica · consegna P2

Perimetro di collaudo sintetico. I nuovi flussi richiedono un professionista verificato, MFA, appartenenza attiva alla struttura e relazione di cura con il paziente. Si applica il gate di rilascio del [QMS](qms/README.md).

## Identificazione e acquisizione

- Registrare presso una fonte verificata un identificativo locale, un codice fiscale personale o il numero della tessera sanitaria tramite `POST /api/v1/clinical/patients/{id}/identifiers/`. Il portale professionista offre il modulo sotto **Documenti clinici**. Il sistema confronta la data di nascita con quella dell'anagrafica e registra autore e tenant. Per il codice fiscale controlla struttura, carattere di controllo e data codificata, comprese sostituzioni omocodiche. Per la tessera controlla solo il formato numerico. La verifica presso registri ufficiali resta aperta.
- Il backend conserva un HMAC della combinazione tenant, tipo e identificativo normalizzato. L'identificativo in chiaro non viene salvato né restituito. L'unicità è applicata per tenant e tipo. La registrazione non consente di spostare un identificativo a un altro paziente. La chiave `CLINICAL_IDENTITY_KEY` è indipendente dalla chiave di sessione e va conservata con i backup. Poiché il dato originale non è conservato, una sostituzione della chiave richiede un piano di nuova acquisizione da fonte verificata.
- Per registrare un episodio o associare un referto usare `identifier_kind`, `identifier_value` e `source_birth_date` dalla fonte originale. Lo UUID del percorso seleziona il record e non sostituisce uno dei due controlli. L'associazione fallisce se un dato manca o non corrisponde. Il controllo vale per referti strutturati e upload/nuove versioni di documenti classificati **Referto**. La classificazione del file è responsabilità del professionista. Gli import amministrativi legacy restano separati e non costituiscono un percorso verificato.
- L'HMAC è ancora dato pseudonimizzato. L'unicità rileva il riuso dello stesso identificativo, mentre anagrafiche duplicate con identificativi diversi richiedono indagine. Le registrazioni restano immutabili e la correzione degli identificativi richiede un workflow di governance prima dell'uso reale.

## Episodi, referti e storico

- `POST /api/v1/clinical/patients/{id}/encounters/` registra un episodio ambulatoriale concluso. Sono richiesti inizio e fine, con periodo ordinato e non futuro. La lettura FHIR R4 usa `GET /api/v1/fhir/Encounter/{id}`.
- `POST /api/v1/clinical/patients/{id}/reports/` crea un referto strutturato e le osservazioni nella stessa transazione. L'episodio facoltativo deve appartenere al paziente. L'autore del referto con relazione di cura ancora valida può aggiungere una correzione a `POST /api/v1/clinical/reports/{id}/corrections/`. Il payload include l'intero contenuto sostitutivo, la motivazione, i due dati identificativi e `expected_version`. Una richiesta su versione obsoleta riceve 409.
- `GET /api/v1/fhir/DiagnosticReport/{id}` restituisce l'ultima versione visibile al chiamante. `/_history/{version}` restituisce una versione specifica. Il parametro `as_of` sulla lettura corrente seleziona una versione registrata entro un istante ISO 8601 con offset. I record legacy privi di data di registrazione restano leggibili per ID e non vengono inclusi nelle ricerche temporali.
- `GET /api/v1/fhir/Provenance/{id}-v{version}` lega una nuova versione al suo autore e al timestamp del sistema. È provenienza applicativa. Le nuove versioni strutturate e le osservazioni sono `preliminary` e visibili al team di cura. Un destinatario con un grant o il paziente non accede a queste bozze. I referti strutturati precedenti conservano i permessi di lettura e sono marcati `unknown`, senza timestamp o firma inventati.
- I trigger PostgreSQL bloccano UPDATE/DELETE per referti, osservazioni, episodi e identificativi. Scrittura API e audit sono transazionali. Un amministratore DB privilegiato rimane fuori dal perimetro di immutabilità dimostrato. Le politiche di conservazione e gli accessi diretti del runtime al DB restano oggetto di P6/P10.

## Terminologia e unità

Il profilo locale versionato `claria-lab-1` accetta il codice di referto generico LOINC `11502-2` e due codici di osservazione per glucosio. `2345-7` richiede `mg/dL`. `14749-6` richiede `mmol/L`. Il confronto usa la forma UCUM case-sensitive. Il sistema rifiuta coppie incompatibili e non converte valori tra concentrazione di massa e di sostanza. Gli intervalli sono trascritti dalla fonte, con limiti, laboratorio ed eventuale contesto di età e sesso. L'app non sceglie intervalli, non applica soglie cliniche e non inferisce il contesto del paziente.

Fonti del mapping. [LOINC 11502-2](https://loinc.org/11502-2) · [LOINC 2345-7](https://loinc.org/2345-7) · [LOINC 14749-6](https://loinc.org/14749-6) · [Licenza LOINC](https://loinc.org/license/) · [Specifiche UCUM](https://ucum.org/ucum) · [FHIR R4 DiagnosticReport](https://hl7.org/fhir/R4/diagnosticreport.html) · [Observation](https://hl7.org/fhir/R4/observation.html) · [Encounter](https://hl7.org/fhir/R4/encounter.html)

## Calcolatori e punteggi

**DA VALIDARE da professionista abilitato.** Funzioni pure con versione e test. Rimangono fuori dai flussi utente, di diagnosi e di dosaggio.

- BMI metrico in kg/m², senza classificazione automatica. [CDC](https://www.cdc.gov/bmi/adult-calculator/)
- eGFR CKD-EPI creatinina 2021 per adulti, in mL/min/1,73 m², con creatinina standardizzata in mg/dL e coefficiente selezionato esplicitamente. L'app non inferisce il coefficiente dall'anagrafica. [NIDDK](https://www.niddk.nih.gov/research-funding/research-programs/kidney-clinical-research-epidemiology/laboratory/glomerular-filtration-rate-equations/adults)
- Energia dei tre macronutrienti in kcal. Carboidrati esclusi i polioli. Il calcolo non stima il fabbisogno o l'energia di una dieta che include altre fonti. [Regolamento UE 1169/2011, allegato XIV](https://eur-lex.europa.eu/eli/reg/2011/1169/oj)
- Somma dei punteggi PHQ-9 e GAD-7, con rifiuto di item mancanti o fuori scala. Nessuna raccolta delle risposte, classificazione o valutazione del singolo item è esposta. [PHQ-9](https://pubmed.ncbi.nlm.nih.gov/11556941/) · [GAD-7](https://doi.org/10.1001/archinte.166.10.1092)

## Requisiti P2 aperti

- Merge/unmerge dei pazienti e rollback di legami, consensi, audit e contenuti. Nessuna fusione automatica. Minori, capacità decisionale, tutori, caregiver e deleghe restano fuori dal flusso.
- Problem list, anamnesi strutturata, allergie, vaccinazioni, parametri vitali, procedure, piani di cura, terapie, richieste, AuditEvent FHIR e template per visita, nutrizione e psicologia restano da completare. Rimane disponibile il precedente isolamento delle note psicologiche. I soli punteggi matematici non costituiscono il modulo psicologico.
- Cataloghi completi e import con licenze e versioni, in particolare SNOMED CT, ICD, ATC e AIC. Mapping ai profili italiani e IPS e validazione con il validatore HL7 restano aperti.
- Firma elettronica PAdES/CAdES, marca temporale e conservazione. L'adapter futuro deve associare firmatario, artefatto esatto e versione, verificare catena, revoca e marca temporale e registrare prova e ricevuta di conservazione prima della pubblicazione. Le bozze nuove restano riservate senza questo gate.
- Le correzioni riguardano i referti strutturati. Gli episodi conclusi sono append-only e non hanno ancora un workflow di rettifica. Per gli upload il sistema distingue i documenti sorgente da un referto strutturato prodotto e revisionato nel portale. La visibilità dei documenti sorgente segue il precedente modello di accesso.

## Verifica locale

Eseguire `make dev` per generare la configurazione locale e applicare le migrazioni `0031` e `0032`. Usare solo fixture. Eseguire `make check`, `make test` e il [controllo QMS](qms/README.md). Le rotte FHIR qui documentate passano tramite il proxy Compose.

### Evidenze tecniche locali

- 58 test Django passati con ClamAV e S3. Copertura complessiva `identity` **83,55%**. Il target globale resta 85%.
- Il test dedicato ai calcolatori copre **37 istruzioni e 18 rami su 18**. Il gate 100% è inserito nella configurazione CI. L'esito CI remoto resta da verificare.
- Upgrade sintetico da `0030` a `0032` provato con referto e osservazione preesistenti. Valori e identificativi sono preservati, senza ricostruire una data di registrazione.
- 22 test Node, controlli SQLite, quattro prove QMS e 26 scenari browser complessivi. L'AI viene provata con fixture nuova e task Django su DB isolato.
- OpenAPI rigenerata e validata. Ruff, ESLint, mypy, TypeScript e build Next passati. Bandit senza esiti medi/alti, Semgrep senza rilevazioni, pip-audit backend senza advisory e npm senza alti o critici. Restano sette advisory npm bassi o moderati e gli advisory dell'immagine imaging già registrati in P1.
