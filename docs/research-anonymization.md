# M7 — Consenso e anteprima degli aggregati

Il primo incremento consente al paziente collegato di dare e revocare il consenso per statistiche aggregate su osservazioni di laboratorio. Gli eventi registrano versione, attore, esito e data. Il database impedisce modifiche e cancellazioni ordinarie. Il consenso è separato dalle condivisioni cliniche. Se cambia il collegamento del paziente, il consenso del precedente account non è utilizzabile.

La proiezione iniziale raggruppa per anno e codice analita e conta account distinti con consenso attivo e corrente. Più osservazioni dello stesso account non aumentano il conteggio. Una cella compare solo con almeno dieci account. Non vengono selezionati risultati di laboratorio, nomi, date esatte, sedi o identificatori nel risultato. Un codice è controllato solo per sintassi. Il comando amministrativo `python manage.py research_preview` restituisce esclusivamente il numero di celle eleggibili, senza produrre un dataset. Ogni esecuzione ricalcola i consensi correnti.

La soglia è una misura di minimizzazione. La valutazione di differenze fra versioni, incroci e rischio di re-identificazione deve precedere la pubblicazione di dataset o aggregati. Restano aperti archivio separato, ETL persistente e versionato, pseudonimizzazione, catalogo e dizionario, terminologie, richieste approvate, dashboard ed export.

## Archivio aggregato separato

Configurare RESEARCH_DATABASE_DSN con una base PostgreSQL dedicata e un ruolo di scrittura riservato all'operatore ETL. Il comando rifiuta un database con lo stesso nome di quello clinico. Eseguire `python manage.py research_refresh` per pubblicare internamente la proiezione fissa `laboratory-account-counts-v1`. Il database destinazione riceve solo anno, codice, conteggio e metadati della versione. Il digest rende il replay idempotente e la transazione sostituisce l'intera proiezione, comprese le celle scese sotto soglia dopo una revoca. Le righe sostituite non sono conservate come versioni consultabili.

La revoca ha effetto sul database clinico alla registrazione e sull'archivio al successivo refresh riuscito. Eseguire un refresh prima di qualsiasi uso operativo. L'archivio è riservato agli operatori e privo di endpoint pubblici. Restano aperti scheduling, policy per differenze tra snapshot, catalogo, valutazione dei dati pseudonimi e workflow di richiesta ed export.
