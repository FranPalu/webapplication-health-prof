# P3 · Regole di laboratorio e presa visione

**DA VALIDARE da professionista abilitato.** Questa consegna è un incremento P3 per fixture sintetiche. L'applicazione richiede `CLINICAL_SAFETY_ENABLED=1` e `DJANGO_DEBUG=true`. Il valore predefinito è disattivato. Nessuna soglia clinica è distribuita con il codice. Usare un database sintetico isolato. La migrazione `0034` aggiunge regole, approvazioni e coda senza attribuire retroattivamente valutazioni ai referti esistenti.

## Configurazione e valutazione

1. Il professionista verificato della struttura propone una regola tramite `POST /api/v1/organizations/{org_id}/lab-rules/`. Deve indicare analita, unità UCUM, laboratorio, età, eventuale contesto di sesso, almeno un limite, SLA, riferimento documentale e professionista di escalation. Il backend valida l'unità rispetto al codice e blocca limiti invertiti.
2. Un altro professionista verificato, con ruolo admin attivo nella stessa struttura, approva tramite `POST /api/v1/organizations/{org_id}/lab-rules/{rule_id}/approve/`. Le versioni e le approvazioni sono append-only. Per ritirare una regola si propone e approva una nuova versione disabilitata per lo stesso gruppo. L'approvazione tecnica non verifica l'appropriatezza clinica della fonte.
3. Ogni nuova versione di referto strutturato crea una voce di coda nella stessa transazione. La regola deve corrispondere esattamente a struttura, laboratorio, codice, unità e contesto. L'età è calcolata rispetto alla data del referto. Il campo facoltativo `evaluation_sex` deve essere trascritto esplicitamente dalla fonte quando richiesto dalla regola. Non viene dedotto dalla data, dal codice fiscale o dall'intervallo di riferimento. Dati assenti, unità incompatibili, limiti non utilizzabili o più regole applicabili producono **dato insufficiente**. Gli estremi sono inclusivi. Le soglie critiche sono distinte dagli intervalli di riferimento riportati nel referto.
4. La coda mostra anche le revisioni entro i limiti configurati e quelle con dato insufficiente. Si conserva l'ID di ogni regola applicata. Una correzione del referto genera una nuova voce. La presa visione della precedente rimane riferita alla versione originaria.

La configurazione locale e la presa visione con escalation seguono principi pubblicati per la comunicazione dei risultati ad alto rischio. I valori del test sono convenzioni sintetiche. [Consensus Statement sulla gestione dei risultati ad alto rischio](https://pmc.ncbi.nlm.nih.gov/articles/PMC4745612/)

## Coda, notifica ed escalation

- Nella scheda paziente, **Referti da prendere in visione** mostra la coda per il team di cura. La conferma visualizza nome e data di nascita, mentre l'API verifica l'ID del paziente inviato. Il link apre la versione esatta del referto tramite il proxy Compose.
- Il risultato critico crea una notifica in-app e una richiesta di email generica per l'autore del referto. Nessun valore, nome del paziente o identificativo del referto compare nell'email. Quando più regole segnalano criticità, il termine più breve determina la prima escalation.
- Celery Beat controlla la scadenza ogni minuto. Il worker acquisisce un lock per voce, rivaluta l'accesso del referente e registra un solo tentativo. Se il referente non è più autorizzato, l'escalation è marcata **senza destinatario**, resta visibile in coda e richiede intervento manuale. La presa visione è idempotente e auditata. La creazione della notifica o il tentativo di invio email non dimostrano consegna.
- La presa visione non firma, non pubblica e non modifica il referto. I referti nuovi restano preliminari e riservati al team di cura.

## Limiti ancora aperti

- Ordini di esame, associazione obbligatoria ordine–risultato e chiusura dopo revisione. La coda attuale inizia dal referto ricevuto.
- Interazioni farmaco-farmaco e farmaco-allergia, duplicazioni, dosi, controindicazioni, fonte farmacologica licenziata e override motivato.
- Conferma del paziente su firma, invio e prescrizione, oltre alla presa visione coperta. Workflow di sostituzione per referenti assenti, affidabilità e retry della consegna, eventuale SMS.
- Validazione clinica di soglie, coorti, età, ruoli, SLA, turni, procedure di laboratorio e scenari multidisciplinari. Il collaudo non abilita l'uso come allarme primario o in urgenza.

## Riproduzione

Avviare lo stack sintetico con `make dev`, attivare il flag nella configurazione locale e riavviare i servizi Compose interessati. Configurare regole sintetiche solo con due account verificati di prova. Eseguire `make check` e `make test`. `test_clinical_safety.py` contiene 132 scenari parametrici su limiti, unità e assenza di regola, più scenari su contesto e sul workflow reale Django. Il test Playwright della coda intercetta l'API per provare la conferma e i messaggi UI. I test Django verificano le autorizzazioni, gli effetti a database e le email generiche.
