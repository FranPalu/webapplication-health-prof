# ADR 0010 · Titolo d'accesso corrente nei flussi di condivisione

**Stato** Accettato per P0, per il perimetro sintetico.

Il consenso già concesso e l'identità di chi ha creato un grant non bastano per consultare i messaggi quando viene meno il titolo corrente del concedente. L'azione di ri-condivisione di un grant padre è riservata al destinatario attualmente autorizzato. Il concedente che conserva accesso diretto può creare una condivisione indipendente con il relativo consenso. Per messaggi su cartella, documento o dossier si applica la versione minima clinica. I grant anagrafici singoli conservano il comportamento v1.

Le liste cliniche di cartelle e job AI registrano le letture prima della risposta. Gli eventi includono ID e tenant, senza titolo della cartella o contenuto della bozza. Nessuna migrazione è necessaria per questi cambiamenti. I messaggi conservati restano soggetti alle politiche di retention e alle autorizzazioni correnti.

Limiti e decisioni rinviate in [P0](../p0/gap-analysis.md) e [Clinical Validation Log](../p0/clinical-validation-log.md).
