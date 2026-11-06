# SRS e piano di verifica e validazione

I requisiti di sicurezza iniziali SRS-01…SRS-20 sono in [register.json](register.json). Ogni voce identifica comportamento richiesto, hazard, tracciabilità P0, fase, test esistenti e prova di uscita. Un riferimento a un test esistente dimostra solo il controllo parziale espressamente coperto. Per esempio il test di attestazione interna non prova la firma elettronica.

## Matrice di esecuzione

| Livello | Metodo e criteri | Evidenza e responsabilità |
| --- | --- | --- |
| Revisione requisiti e rischio | Ogni hazard è collegato a requisito, prova attesa, fase, owner e residuo. Ogni riferimento esistente risolve a un test. I punteggi clinici restano da validare | Gate `check_qms.py`, verifica a cura della qualità, revisione clinica separata |
| Unità e proprietà | Limiti, conversioni, decisioni di accesso, casi insufficienti. Copertura ≥85% core e 100% di calcolatori e regole di autorizzazione | Report CI per commit e perimetro. Test funzionali di ramo e invarianti oltre alla copertura |
| Integrazione | PostgreSQL, concorrenza, scanner/storage, Celery e contratti esterni. Verifica positiva e negativa di tenant, ruolo, revoca e audit per ogni endpoint sensibile | Fixture sintetiche, dipendenze e configurazione fissate. QA e security |
| Sistema e sicurezza | E2E critici, verifica di recupero, sicurezza applicativa, latenza e accessibilità. Il test pre-firma deve provare che nessun canale paziente esponga la bozza | Playwright, audit SAST/SCA, benchmark p95 <500 ms con carico dichiarato, ASVS e prove di restore |
| Validazione clinica e usabilità | Protocollo approvato prima di vedere risultati. Popolazione e uso rappresentativi, comparatore, lettura indipendente, fallimenti attesi, criteri di arresto e analisi per sottogruppo | Professionisti abilitati e responsabile sicurezza. Dataset sintetico per QA, piano separato per dati e studi autorizzati |
| Validazione modelli e regole | Documentare versione, hash, fonte, matrice confusione, sensibilità, specificità, PPV/NPV, AUC e calibrazione dove applicabili, IC e qualità dei casi. Soglie minime approvate prima di test. Verificare OOD, assenza di dati e fallback | Protocollo P3/P4 e report indipendente. Conservare anche i risultati negativi e le deviazioni |
| Release | Tutti i gate applicabili passano, controlli e residui approvati, codice e build rintracciabili, formazione e piano di rollback pronti | Qualità prepara il dossier. Clinica, security, DPO e regolatorio approvano il rispettivo perimetro. Autorità di rilascio da designare |

Per ogni prova conservare ID requisito e hazard, protocollo, commit, configurazione, versione dei dati/modelli, ambiente, esito atteso e osservato, log depurato, autore, revisore e anomalie. Qualsiasi requisito respinto torna in correzione e re-test. Il piano non attribuisce valore clinico alla sola copertura tecnica.

Le prove P1 sono in [verification.md](verification.md). P2 deve estendere la SRS per entità cliniche, merge/unmerge, UCUM e firma prima di implementare i controlli.
