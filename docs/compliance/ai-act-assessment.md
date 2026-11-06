# AI Act Assessment · valutazione preliminare

**DA VALIDARE da professionista abilitato.** Rilevazione 6 novembre 2026. Analisi per singolo sistema, intended purpose, versione e ruolo dell'operatore. Il fabbricante deve accertare il ruolo di provider. Le strutture utilizzatrici devono accertare quello di deployer. Modifiche sostanziali, nuova destinazione o nuova immissione possono cambiare il ruolo.

## Classificazione

Per l'imaging e il CDS candidati a MDSW, l'ipotesi di progetto è **high-risk condizionato** ai due elementi dell'art. 6(1). Il sistema AI è il prodotto o una sua componente di sicurezza disciplinata dalla legislazione dell'allegato I e il prodotto richiede valutazione di conformità da parte di terzi. Il team regolatorio deve confermare le condizioni dopo la qualificazione MDR/IVDR. Valutare separatamente l'art. 6(2) e l'allegato III per un'eventuale funzione diversa, ad esempio triage d'emergenza, fuori dall'intended use attuale. Le regole deterministiche e la sola trascrizione vanno esaminate sulla definizione di sistema AI e sul funzionamento effettivo. La disponibilità di un modello open o la presenza di un revisore non chiudono la valutazione. [AI Act consolidato, artt. 3 e 6](https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/eng) · [MDCG 2025-6 / AIB 2025-1](https://health.ec.europa.eu/document/download/b78a17d7-e3cd-4943-851d-e02a2f22bbb4_en?filename=mdcg_2025-6_en.pdf)

## Calendario vigente

- **2 febbraio 2025.** Applicazione dei capi I e II, comprese alfabetizzazione AI e pratiche vietate, fatte salve le specifiche eccezioni dell'art. 113(a) aggiunte dall'Omnibus con applicazione dal 2 dicembre 2026.
- **2 agosto 2025.** Prima applicazione delle disposizioni anticipate elencate nell'art. 113(b), tra cui le principali disposizioni GPAI, secondo le transizioni applicabili.
- **2 agosto 2026.** Data generale di applicazione secondo art. 113, con eccezioni. Valutare separatamente trasparenza art. 50 e la transizione art. 111(4) fino al 2 dicembre 2026 per sistemi generatori già immessi prima della data generale.
- **2 dicembre 2027.** Capo III, sezioni 1–3, con eccezione dell'art. 6(5), per high-risk art. 6(2)/allegato III.
- **2 agosto 2028.** Stesse sezioni per high-risk art. 6(1)/allegato I, ipotesi rilevante per i moduli AI candidati a dispositivo.

Verificare regime transitorio e versioni effettive al rilascio. Il calendario usa il regolamento adottato, art. 1 punti 39–40, e il testo consolidato. [Regolamento (UE) 2026/1744, Digital Omnibus](https://eur-lex.europa.eu/eli/reg/2026/1744/oj) · [AI Act consolidato, artt. 111 e 113](https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/eng)

## Controlli e prove

| Area | Stato osservato | Evidenza da completare |
| --- | --- | --- |
| Rischio e qualità | Registro P1, separazione della demo | Applicare QMS con responsabili, gestione del rischio lungo il ciclo, evidenze e riesame indipendente |
| Dati e governance | Fixture sintetiche, versioni e vincoli sulle fonti supportate | Inventario provenienza/diritti, rappresentatività, qualità, errori e sottogruppi. Definire esclusioni, protezione dati e controllo dei cambiamenti |
| Documentazione e logging | Hash input, audit e separazione draft/parere, metadati di pipeline | Log coerenti e verificabili per modello/versione e riesame, retention, fascicolo art. 11 e istruzioni art. 13 |
| Supervisione e trasparenza | Etichetta preliminare, attestazione interna e pubblicazione esplicita nei flussi provati | Firma, competenza e autorità del revisore, rilevazione dell'automazione eccessiva, stop/override, verifica fonti e UI. Analisi art. 50 per ciascun output |
| Accuratezza, robustezza, cybersicurezza | Golden test limitati e imaging offline di collaudo | Metriche e soglie predefinite, calibrazione e OOD, analisi sottogruppi, prove di abuso/input ostili, kill-switch e rollback |
| Operatività | Procedure P1 in bozza, ruoli da designare | Monitoraggio post-market, incidenti, conformità integrata ove applicabile, addestramento e istruzioni per i deployer |

I controlli di progetto sono mappati agli artt. 9–15. Valutare, a seconda del ruolo e del perimetro, anche artt. 16–17, 26–27, 43 e 72–73. La prova clinica e la qualificazione restano aperte. [AI Act consolidato](https://eur-lex.europa.eu/eli/reg/2024/1689/2026-07-27/eng)
