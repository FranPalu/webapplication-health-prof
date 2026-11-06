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

## Revisione simulata P2

**DA VALIDARE da professionista abilitato** per ogni voce. Nessuna delle seguenti prove tecniche costituisce validazione clinica.

| ID | Decisione e ruolo simulato | Caso limite e verifica attesa |
| --- | --- | --- |
| CV-P2-01 | Data di nascita e identificativo registrato · Internista, infermiere | Due omonimi possono condividere la data di nascita. Provare doppia fonte, dati del referto incoerenti e tentativo di riuso nel tenant |
| CV-P2-02 | Nessuna fusione automatica · DPO, risk manager | Una fusione può propagare autorizzazioni o associare una nota al paziente sbagliato. Definire dual review, rollback e informazione ai curanti |
| CV-P2-03 | Referti preliminari, storia e provenienza · Patologo clinico | Una bozza o un dato storico senza firma possono essere scambiati per referto definitivo. Verificare accesso diretto, storico, rettifica e flusso firma |
| CV-P2-04 | Coppie LOINC/UCUM e range della fonte · Patologo clinico | Confondere mg/dL con mmol/L può cambiare l'interpretazione. Provare rifiuto della coppia e verificare eventuali conversioni in un protocollo separato |
| CV-P2-05 | Episodio ambulatoriale e collegamenti · Medico di medicina generale | Un paziente può avere episodi contemporanei. Verificare corrispondenza paziente/struttura e flusso di rettifica prima dell'uso reale |
| CV-P2-06 | Calcolo isolato · Nefrologo simulato, nutrizionista, psicologo | Un eGFR può essere usato impropriamente per dosi, e il totale PHQ-9 può nascondere un item critico. Validare popolazione, input e comportamento clinico prima di esporre i calcoli |
