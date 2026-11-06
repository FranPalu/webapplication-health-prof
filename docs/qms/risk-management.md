# Piano di gestione del rischio · FMECA e HAZOP

**DA VALIDARE da professionista abilitato.** Il [registro hazard](register.json) è la fonte controllata. La baseline include 18 scenari. Tutti risultano bloccanti per uso clinico reale finché il responsabile del rischio e i revisori non hanno valutato e firmato il rischio residuo.

## Metodo

1. Definire destinazione, confine, utenti, flussi e contesto di esposizione. Considerare uso corretto, uso scorretto prevedibile, guasti concorrenti, dipendenze e guasti comuni.
2. Eseguire FMECA per funzione. Registrare modalità di guasto, causa, effetto, gravità S, probabilità P e rilevabilità D. Gli score sono prioritizzazione ingegneristica preliminare. La probabilità è un giudizio su esposizione e barriere, senza tassi clinici stimati. Per la priorità, moltiplicare S×P×D. Una conseguenza di gravità 4 richiede revisione dedicata indipendentemente dal prodotto.
3. Eseguire HAZOP lungo le transizioni identificazione → acquisizione → associazione → estrazione → revisione/firma → consegna → revoca/restore. Per ogni deviazione seguire il relativo hazard e la verifica nel registro.
4. Preferire eliminazione del rischio e limiti per progettazione, poi barriere, infine informazioni e formazione. Registrare i rischi nuovi introdotti dal controllo e le interazioni tra controlli.
5. Per il residuo, documentare S/P riesaminati, popolazione, test, risultati, rischi emergenti, titolare e approvazione. Dove mancano dati clinici il residuo rimane aperto. L'accettazione del rischio e l'eventuale analisi beneficio/rischio richiedono la procedura e i firmatari reali.

| Score | Gravità | Probabilità preliminare | Rilevabilità prima dell'effetto |
| --- | --- | --- | --- |
| 1 | Disagio lieve | Richiede combinazione di condizioni insolite | Barriera automatica verificata |
| 2 | Danno lieve o temporaneo | Possibile in condizioni specifiche | Segnale verificabile all'operatore |
| 3 | Danno significativo o divulgazione rilevante | Plausibile nel flusso in assenza di barriere robuste | Rilevazione manuale incostante |
| 4 | Lesione grave o morte plausibile | Frequente o facilmente riproducibile nella condizione valutata | Errore latente o rilevato dopo l'effetto |

## HAZOP per flusso

| Nodo | Parola guida e deviazione | Azione da verificare |
| --- | --- | --- |
| Accesso e associazione | Altro paziente, altro tenant, altro referto | H-01/H-05/H-10. Doppio identificatore, contesto visibile, isolamento e rifiuto mismatch |
| Acquisizione e semantica | Meno dati, unità diversa, valore duplicato | H-04/H-14/H-16. Scanner, profilo, unità UCUM, provenienza e validazione all'import |
| Valutazione | Nessun alert, valore troppo alto/basso, altra dose | H-06/H-13/H-18. Regole approvate, soglie contestuali, qualità/OOD e override auditato |
| Pubblicazione e presa in carico | Troppo presto, troppo tardi, nessun destinatario | H-06/H-15/H-17. Firma, blocco pre-pubblicazione, ack ed escalation |
| Consenso e ricerca | Dopo revoca, più accessi o più granularità | H-02/H-03/H-09. Rivalutazione, audit indipendente, disclosure e prova di revoca |
| Continuità e ripristino | Nessun servizio, dati incompleti o obsoleti | H-04/H-11. Restore congiunto, checksum e procedura downtime |
| Prenotazione, farmacia, pagamento | Duplicato, altro importo, verifica assente | H-07/H-08. Idempotenza, verifica ricetta, coerenza dello stock |
| Controllo delle modifiche | Troppo presto o senza prova | H-12. Gate, revisione indipendente e controllo dell'impatto |

Aggiornare il registro a ogni modifica di intended use, popolazione, dati, modelli, regole, interfacce, infrastruttura o rischio noto, e dopo incidenti e CAPA. Il responsabile qualità conduce la revisione periodica del registro. I ruoli nel registro indicano responsabilità da assegnare. Il Clinical Validation Log registra revisione simulata, prova attesa e limiti.
