# Clinical Validation Log · P1

**DA VALIDARE da professionista abilitato** per ogni voce. Revisione simulata, 6 novembre 2026. Stato di tutte le voci: in attesa di un revisore clinico reale e della prova indicata. [Registro rischi](register.json) · [Voci P0](../p0/clinical-validation-log.md)

| ID | Decisione e ruolo simulato | Rischio per il paziente o caso limite | Prova o approvazione attesa |
| --- | --- | --- | --- |
| CV-P1-01 | Adulti, contesti programmati, esclusione minori e urgenze · MMG, internista | Un operatore può tentare di usare il flag durante un'urgenza o scambiare l'assenza di alert per un dato normale | Criteri di inclusione/esclusione, validazione UI/IFU e procedura di escalation alternativa |
| CV-P1-02 | Confine software C conservativo · Risk manager, infermiere | Un modulo tecnico apparentemente separato può rompere identificazione, consegna o integrità | Prova di segregazione, analisi guasti comuni e riesame classi con referente clinico |
| CV-P1-03 | Doppio identificatore, storia e UCUM · Internista, patologo clinico | Omonimia, unità diverse e doppio referto possono trasformare un dato corretto in un'informazione pericolosa | Convalida dei casi H-01/H-05/H-16 e scenari di import/merge |
| CV-P1-04 | Risultati critici, farmaci ed escalation · Patologo, farmacista ospedaliero, infermiere | Una consegna provider non prova che il clinico abbia letto il risultato. Dati mancanti possono rendere insicuro un controllo posologico | Prove di presa in carico, fuori orario, fallback e fonti licenziate |
| CV-P1-05 | Distinzione OCR, interpretazione IVD e AI imaging · Radiologo, patologo, regolatorio | Output di provenienza mista, campione errato e modalità fuori distribuzione possono indurre falsa rassicurazione | Destinazione e classe firmate, protocollo indipendente con soglie, comparatore e sottogruppi |
| CV-P1-06 | Gate conservativo e CAPA · Risk manager clinico, DPO | Un risultato parziale o una variazione dopo la validazione può essere trattato come prova sufficiente | Verificare evidenze, approvazioni indipendenti, stop/rollback e tabletop |
| CV-P1-07 | Audit, note riservate e ricerca · Psicologo clinico, DPO | Un audit non attribuibile o un aggregato troppo fine può esporre pazienti e danneggiare la fiducia | Scenari di revoca, audit privilegiato e rischio di re-identificazione |
| CV-P1-08 | Modelli e SOUP controllati · Radiologo, sicurezza clinica | Aggiornamento di parser o dipendenza può alterare fonti, tempi o riproducibilità senza modificare l'interfaccia | Riesame per digest/versione, confronto golden e valutazione licenze/pesi |
| CV-P1-09 | Conferme UI e continuità · Nutrizionista, MMG, infermiere | Se l'interfaccia perde il contesto o il servizio si interrompe, l'operatore può applicare un piano al paziente sbagliato | Usabilità rappresentativa e prova di downtime con responsabilità esplicita |
