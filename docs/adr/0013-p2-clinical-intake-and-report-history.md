# ADR 0013 · Identificazione alla fonte e referti append-only

**Stato** Accettato per il collaudo sintetico P2.

Il team di cura conferma la data di nascita e un identificativo già registrato nello stesso tenant. Usare un HMAC con chiave dedicata minimizza i dati conservati. L'unicità previene il riuso esatto, mentre un conflitto o una fusione richiede revisione umana. La versione di referto è append-only, con autore e motivo, controllo ottimistico del chiamante e serializzazione delle correzioni sulla radice. Le letture storiche usano i permessi correnti. La firma e la validazione del provider sono prerequisiti distinti per la pubblicazione dei referti strutturati nuovi.

Le scritture adottano un profilo di laboratorio ridotto, con rifiuto di unità e codici non supportati e dati di range riportati dalla fonte. I record storici non ricevono nuovi codici UCUM o date presunte. Il [documento P2](../10-clinical-record-p2.md) elenca conseguenze, migrazioni e limiti. [Riesame clinico](../qms/clinical-validation-log.md)
