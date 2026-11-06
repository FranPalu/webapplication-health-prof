# P3 · Regole di laboratorio e presa visione

**DA VALIDARE da professionista abilitato.** Questa consegna documenta il perimetro P3 verificabile con fixture sintetiche. L'applicazione richiede `CLINICAL_SAFETY_ENABLED=1` e `DJANGO_DEBUG=true`. Il valore predefinito è disattivato. Nessuna soglia clinica è distribuita con il codice. Usare un database sintetico isolato. Le migrazioni `0034`–`0036` aggiungono regole, coda, ordini e screening. I referti preesistenti non ricevono valutazioni retroattive.

## Configurazione e valutazione

1. Il professionista verificato della struttura propone una regola tramite `POST /api/v1/organizations/{org_id}/lab-rules/`. Deve indicare analita, unità UCUM, laboratorio, età, eventuale contesto di sesso, almeno un limite, SLA, riferimento documentale e professionista di escalation. Il backend valida l'unità rispetto al codice e blocca limiti invertiti.
2. Un altro professionista verificato, con ruolo admin attivo nella stessa struttura, approva tramite `POST /api/v1/organizations/{org_id}/lab-rules/{rule_id}/approve/`. Le versioni e le approvazioni sono append-only. Per ritirare una regola si propone e approva una nuova versione disabilitata per lo stesso gruppo. L'approvazione tecnica non verifica l'appropriatezza clinica della fonte.
3. Ogni nuova versione di referto strutturato crea una voce di coda nella stessa transazione. La regola deve corrispondere esattamente a struttura, laboratorio, codice, unità e contesto. L'età è calcolata rispetto alla data del referto. Il campo facoltativo `evaluation_sex` deve essere trascritto esplicitamente dalla fonte quando richiesto dalla regola. Non viene dedotto dalla data, dal codice fiscale o dall'intervallo di riferimento. Dati assenti, unità incompatibili, limiti non utilizzabili o più regole applicabili producono **dato insufficiente**. Gli estremi sono inclusivi. Le soglie critiche sono distinte dagli intervalli di riferimento riportati nel referto.
4. La coda mostra anche le revisioni entro i limiti configurati e quelle con dato insufficiente. Si conserva l'ID di ogni regola applicata. Una correzione del referto genera una nuova voce. La presa visione della precedente rimane riferita alla versione originaria.

La configurazione locale e la presa visione con escalation seguono principi pubblicati per la comunicazione dei risultati ad alto rischio. I valori del test sono convenzioni sintetiche. [Consensus Statement sulla gestione dei risultati ad alto rischio](https://pmc.ncbi.nlm.nih.gov/articles/PMC4745612/)

## Coda, notifica ed escalation

- Nella scheda paziente, **Esami e referti in sospeso** mostra la coda per il team di cura. La conferma visualizza nome e data di nascita, mentre l'API verifica l'ID del paziente inviato. Il link apre la versione esatta del referto tramite il proxy Compose.
- Il risultato critico crea una notifica in-app e una richiesta di email generica per l'autore del referto. Nessun valore, nome del paziente o identificativo del referto compare nell'email. Quando più regole segnalano criticità, il termine più breve determina la prima escalation.
- Celery Beat controlla la scadenza ogni minuto. Il worker acquisisce un lock per voce, rivaluta l'accesso del referente e registra un solo tentativo. Se il referente non è più autorizzato, l'escalation è marcata **senza destinatario**, resta visibile in coda e richiede intervento manuale. La presa visione è idempotente e auditata. La creazione della notifica o il tentativo di invio email non dimostrano consegna.
- La presa visione e il completamento della revisione sono eventi distinti. Entrambi richiedono conferma del paziente. Il completamento richiede una nota. Firma e pubblicazione restano flussi separati. I referti nuovi restano preliminari e riservati al team di cura.

## Richieste, risultati e revisione

- Registrare una richiesta tramite `POST /api/v1/clinical/patients/{id}/lab-orders/` con doppia identificazione, analita LOINC supportato e scadenza. La coda distingue **risultato atteso**, **revisione attesa** e richieste scadute.
- Associare il referto iniziale con `order_id`. Il backend e il vincolo PostgreSQL verificano paziente, analita richiesto e sequenza temporale. Una richiesta ha un solo referto logico. Una correzione deve conservare l'analita richiesto e non cambia la richiesta.
- La presa visione ferma l'escalation. Solo `POST /api/v1/clinical/result-reviews/{id}/complete/`, con paziente e nota, registra la revisione. La richiesta sparisce dalla coda solo dopo la revisione dell'ultima versione. Una nuova correzione la riapre. Le decisioni storiche restano associate alle rispettive versioni.
- La lettura FHIR R4 `ServiceRequest` espone lo stato e il `DiagnosticReport.basedOn` identifica la richiesta. Le letture sono riservate al team di cura nel perimetro sintetico. [FHIR R4 ServiceRequest](https://hl7.org/fhir/R4/servicerequest.html)

## Screening farmacologico

`POST /api/v1/clinical/patients/{id}/medication-checks/` riceve identificazione alla fonte, elenco dei medicinali con codice, via, unità e dose giornaliera, allergeni e condizioni codificati e conferma esplicita della completezza del contesto. L'adapter opzionale `CLINICAL_MEDICATION_PROVIDER` è il percorso Python di una classe amministrata dal deployment. Riceve solo il contesto di screening, senza UUID, nome, data di nascita o identificativo sorgente. Nel collaudo si usa una fonte sintetica iniettata dai test.

Il pannello professionista **Screening farmacologico sintetico** espone gli input, la fonte, il livello di evidenza e la registrazione della motivazione. Il motore verifica interazioni, allergeni, duplicazioni di ingrediente o gruppo, superamento della dose massima e controindicazioni. Ogni esito utilizzabile riporta fonte, versione, riferimento di licenza e livello di evidenza. Ogni segnalazione ha riferimento e livello. Una fonte assente, indisponibile, incompleta o incompatibile con i dati produce **dato insufficiente**. Il motore non propone dosi e non autorizza una prescrizione. `POST /api/v1/clinical/medication-checks/{id}/override/` registra una sola motivazione immutabile per uno screening completo con segnalazioni, con conferma del paziente e audit.

Per un adapter reale verificare diritti di accesso e riuso, versionamento, frequenza di aggiornamento, copertura per via, dose, allergeni e condizioni e corrispondenza dei codici. Gli RCP AIFA sono riferimenti ufficiali da considerare nella validazione. Occorre una fonte strutturata con copertura dimostrata per sostenere uno screening computabile. [AIFA · Riassunto delle caratteristiche del prodotto](https://www.aifa.gov.it/riassunto-caratteristiche-e-foglio-illustrativo)

## Limiti ancora aperti

- Fonte farmacologica licenziata, mappatura con la cartella e validazione indipendente dell’appropriatezza delle soglie e dei controlli.
- Flussi di firma, invio clinico e prescrizione. La conferma e il contesto persistente sono implementati per le operazioni di coda e la conferma API per screening/override.
- Affidabilità della consegna, retry e gestione del referente fuori turno. Le email protette sono provate in collaudo. Un tentativo di invio non attesta consegna. L'eventuale SMS richiede un adapter verificato.
- Validazione clinica di coorti, età, SLA, copertura del laboratorio e scenari multidisciplinari. Il collaudo non abilita l'uso come allarme primario o in urgenza.

## Riproduzione

Avviare lo stack sintetico con `make dev`, attivare il flag nella configurazione locale e riavviare i servizi Compose interessati. Configurare regole sintetiche solo con due account verificati di prova. Eseguire `make check` e `make test`. `test_clinical_safety.py` contiene 132 scenari parametrici su limiti, unità e assenza di regola, più scenari su contesto e sul workflow reale Django. Il test Playwright intercetta l'API per provare coda, conferma, revisione, provenienza e override nelle interfacce. I test Django verificano le autorizzazioni, gli effetti a database e le email generiche.

### Evidenze locali

- Suite Django con PostgreSQL, ClamAV e storage locale, **195 test**. Copertura `identity` **85,12%** e soglia impostata all'85%. Il requisito del 100% delle regole di autorizzazione resta aperto.
- **132 scenari sintetici** per il motore delle soglie, oltre ai test di contesto, escalation, percorso ordine–risultato–revisione e screening farmacologico.
- **22 test Node**, verifiche SQLite, quattro prove QMS e **27 scenari browser** in due esecuzioni. Playwright verifica coda e screening con risposte intercettate. Le prove Django verificano la persistenza e le autorizzazioni effettive.
- Ruff, mypy, ESLint, TypeScript, build Next, migrazioni e OpenAPI verificati. Bandit senza avvisi medi o alti, Semgrep senza rilevazioni, pip-audit backend senza advisory. Il grafo npm conserva sei avvisi moderati e uno basso. L'immagine imaging isolata conserva gli advisory già registrati in P1.
