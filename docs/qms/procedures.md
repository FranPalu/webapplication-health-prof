# Procedure QMS · configurazione, anomalie e ciclo post-market

Edizione di lavoro. I ruoli sono funzioni organizzative da assegnare e separare. Le registrazioni operative devono essere in un ambiente ad accesso controllato, con minimizzazione e retention approvate. Nei report Git usare ID opachi e fixture sintetiche.

## Configurazione e change control

1. Aprire una richiesta con ID, descrizione, ragione, baseline, artefatti e ambito. Includere dipendenze, infrastruttura, regole, modelli/prompt, dati, impostazioni, traduzioni e documenti.
2. Qualità e security classificano l'impatto. I referenti clinico, DPO e regolatorio valutano modifiche a intended use, popolazione, rischio, trattamento, evidenze e possibile valutazione di conformità. Indicare hazard e SRS coinvolti, effetti sull'utilizzo reale, migrazione e rollback.
3. Preparare codice, test e aggiornamenti a registro, SOUP, SOP, training e documentazione. Eseguire prove su build identificabile. Il revisore indipendente verifica correzione, anomalie aperte e criteri di release.
4. Conservare commit e tag, checksum, lockfile, immagini e digest effettivi, configurazione redatta, modello/dataset e report. Firma e data del riesame precedono rilascio. Monitorare l'esito e applicare rollback/kill-switch secondo criterio concordato.

**Modulo richiesta.** ID | Baseline | Impatto clinico e privacy | Hazard/SRS | Verifiche | Migrazione | Rollback | Revisori | Decisione | Data.

## Anomalie e CAPA

| Priorità clinica | Esempio e risposta interna proposta |
| --- | --- |
| C1 · Possibile danno grave, esposizione estesa o perdita di funzione critica | Sospendere il flusso interessato, attivare on-call e referenti clinici subito, proteggere le evidenze |
| C2 · Possibile danno significativo o controllo degradato | Triage entro la giornata lavorativa, workaround verificato e revisione prima del rilascio |
| C3 · Danno lieve plausibile o problema recuperabile | Prioritizzare nel ciclo di correzione, verificare segnalazione e casi analoghi |
| C4 · Nessun impatto clinico identificato | Correggere nel ciclo ordinario, riesaminare se cambia il contesto |

Registrare versione, scenario, effetto, frequenza osservata, riproduzione e segnalante tramite ID controllati. Assegnare owner, contenere, eseguire root cause e analisi d'estensione. Per CAPA documentare correzione immediata, azione sistemica, owner/scadenza, verifica indipendente di efficacia, evidenza osservabile e decisione di chiusura. Un difetto riapre l'hazard se invalida un controllo, una stima o la destinazione dichiarata.

**Modulo CAPA.** ID | Anomalia/hazard | Contenimento | Causa | Azione e scadenza | Misura di efficacia | Evidenza | Firma qualità.

## Incidenti e vigilanza

Ricevere la segnalazione, proteggere il paziente tramite il responsabile assistenziale, contenere e conservare evidenze senza trasferire dati nei ticket. Distinguere evento clinico, incidente cybersecurity, violazione dati e potenziale incidente grave di dispositivo. Valutare più percorsi in parallelo. Qualità e regolatorio determinano notificabilità, decorrenza, autorità, canale, termini e follow-up MDR/IVDR/AI Act secondo il quadro applicabile. Il DPO coordina separatamente l'eventuale notifica di data breach. Registrare orari, decisione motivata, responsabile, rapporti, eventuale azione correttiva sul campo e comunicazione alle strutture. Provare un tabletop prima del pilota.

**Modulo incidente.** ID | Presa in carico | Impatto e pazienti tramite riferimento protetto | Contenimento | Notificabilità e base | Autorità | Azioni | CAPA | Chiusura.

## Sorveglianza post-market e fornitori

Prima del rilascio, qualità approva frequenza, owner, soglie e canali per reclami, near miss, indisponibilità, drift, override, dati incompleti, vulnerabilità e segnalazioni dei fornitori. Riesame interno almeno mensile nel pilota, con escalation immediata dei segnali C1. Registrare denominatori ed esposizione, comparare al baseline, aggiornare rischio e CAPA e decidere sospensione o rollback. Preparare PMS e PMCF, oppure PMS e PMPF se applicabile, e gli output previsti dalla classificazione. La procedura diventa operativa dopo designazione dei ruoli, revisione legale e addestramento.

Per dipendenze e modelli verificare fonte, versione, licenza, anomalie note e rilevanza clinica a ogni aggiornamento. Isolare o sospendere componenti a rischio. Conservare l'inventario e la prova di installazione riproducibile. [Inventario SOUP](soup.md)
