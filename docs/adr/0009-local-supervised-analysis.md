# ADR 0009 — Analisi locale con revisione separata

Il worker Celery elabora una versione immutabile M3 su richiesta esplicita. Il job conserva un lease e viene recuperato in caso di interruzione. Prima della lettura e del salvataggio si ricontrollano feature flag, hash e autorizzazioni del richiedente. Una revoca che si completa durante l'elaborazione impedisce il salvataggio della bozza.

Le regole producono i risultati deterministici. Il modello locale sceglie riferimenti a evidenze senza poter introdurre testo clinico nel riepilogo. La bozza, la decisione e il parere sono separati e cifrati. Il database impedisce modifiche e cancellazioni ordinarie delle attestazioni. Una pubblicazione separata associa il parere allo specifico account paziente collegato al momento della pubblicazione.

Il collaudo imaging è un container senza rete e fuori dalla pipeline clinica. Sono ammessi solo casi sintetici o pubblici autorizzati tramite manifest. La feature referti è disattivata per impostazione predefinita e disponibile solo in DEBUG.
