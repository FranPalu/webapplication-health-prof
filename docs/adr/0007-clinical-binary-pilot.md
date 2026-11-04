# ADR 0007 — Persistenza transazionale per la prima consegna M3

Stato: temporaneo.

I binari di massimo 10 MiB sono cifrati prima della scrittura. Una chiave distinta per versione è avvolta da una chiave derivata per organizzazione. La prima consegna salva il risultato nel database insieme alla versione e all'audit, così un rollback rimuove l'intera scrittura senza lasciare oggetti orfani.

Questa scelta limita la capacità e aumenta il peso dei backup. Prima di chiudere M3, introdurre storage S3 privato e KMS con chiavi versionate, riconciliazione delle scritture e prova di ripristino. La chiave pilota deve restare disponibile per leggere le versioni già salvate. Evitare la sostituzione diretta della variabile d'ambiente mentre esistono versioni da conservare.
