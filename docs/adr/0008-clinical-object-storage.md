# ADR 0008 — Storage dei documenti e indice di ricerca

La transazione di upload scrive versione, audit e binario cifrato nel database. Un job ripetibile trasferisce la versione in un bucket privato e cancella la copia di staging dopo il successo. La chiave oggetto deterministica consente di ripetere una scrittura interrotta. Il riavvolgimento delle chiavi opera sui metadati senza riscrivere i binari. Fuori dallo sviluppo l'avvolgimento di nuovi binari richiede AWS KMS.

L'indice delle parole estratte è composto da HMAC separati per tenant. Consente una ricerca esatta senza salvare il testo estratto. Una frequenza di parole rimane visibile a un operatore con accesso al database. La chiave dell'indice deve essere separata dalle chiavi binarie e dai backup. Il contenuto scansionato o privo di testo richiede OCR in una fase successiva.

Le cartelle e i relativi ambiti sono immutabili dopo la creazione. Le note riservate sono escluse dai grant di cartella e cartella clinica. La versione 2 del consenso esplicita i contenuti e le versioni interessati. I grant esistenti rimangono validi per gli ambiti M2.
