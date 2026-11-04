# M4 — Report di collaudo tecnico

Ambiente locale Docker con PostgreSQL, Celery, ClamAV e SeaweedFS. Fixture sintetiche senza dati identificativi reali. Modelli e hash sono nel [registro M4](05-supervised-analysis.md).

- PDF nativo e PDF scansionato. F1 1,000 su entrambi, con cinque righe esatte per formato. La metrica F1 confronta l'intera tupla analita, valore, unità, limiti e classificazione.
- Regole e casi negativi. Virgole decimali, limiti censurati, intervalli mancanti, unità incoerenti e righe illeggibili. Il confronto riguarda gli intervalli scritti sulla fixture.
- Qwen. Inferenza locale reale con JSON vincolato e verifica dei riferimenti a righe esistenti. Il riepilogo usa i valori estratti dal documento.
- Imaging. Inferenza TorchXRayVision reale su una fixture PA sintetica, 18 punteggi finiti e due inferenze identiche. La stessa fixture dichiarata laterale è stata rifiutata prima dell'inferenza.
- PostgreSQL. Controlli per deduplicazione, retry, revoca durante il job, cifratura, attestazione immutabile, esclusione delle bozze e revisioni concorrenti.
- Browser. Caricamento di un referto sintetico, esecuzione con worker reale, revisione e pubblicazione. L'account paziente vede il solo parere pubblicato. L'URL diretto della bozza restituisce 403.

I risultati misurano il comportamento tecnico sulle fixture. La calibrazione, la validità clinica e la verifica sui formati dei laboratori destinatari restano prerequisiti per un rilascio su dati reali.
