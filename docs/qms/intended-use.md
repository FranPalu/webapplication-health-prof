# Intended Use Statement · bozza controllata

**DA VALIDARE da professionista abilitato.** Versione 0.1. Responsabili della revisione da nominare per clinica, qualità, privacy e regolatorio.

## Utilizzo attuale

Claria è una piattaforma web di collaborazione e un ambiente di sviluppo e collaudo sintetico. Il perimetro attuale è costituito da account di prova e documenti fittizi. Le funzioni sperimentali di elaborazione non sono autorizzate per decisioni cliniche o uso assistenziale reale.

## Destinazione proposta per i moduli clinici

Supporto a professionisti sanitari abilitati nella revisione di documenti e risultati per adulti in percorsi assistenziali programmati. I risultati si riferiscono a un paziente identificato, sono confrontati con la fonte e richiedono conferma esplicita e, prima della visibilità al paziente, firma del professionista. Gli esiti proposti comprendono trascrizione strutturata di referti supportati, evidenza di valori rispetto agli intervalli riportati e segnalazioni di imaging per modalità approvate. Modalità, prestazioni minime e popolazione richiedono validazione prima dell'abilitazione.

| Dimensione | Ipotesi di progetto |
| --- | --- |
| Utenti primari | Clinici abilitati e verificati per attività di revisione. Infermieri per il coordinamento nei limiti del ruolo. Farmacisti per il flusso di prenotazione e verifica di propria competenza |
| Utenti secondari | Pazienti adulti, amministratori senza accesso clinico implicito, ricercatori con accesso a rilasci autorizzati e delegati soltanto dopo convalida del relativo flusso |
| Ambiente | Organizzazioni assistenziali italiane, browser supportati, accessi identificati, rete e storage amministrati, procedure locali di continuità |
| Indicazioni candidate | Revisione di referti con sorgente consultabile, intervalli e unità leggibili e modalità esplicitamente validate. Per imaging la fixture tecnica attuale riguarda una proiezione toracica frontale |
| Controindicazioni ed esclusioni | Minori, emergenze, uso come allarme primario, diagnosi o terapia autonoma, dispensazione autonoma, input illeggibili, gruppi o modalità privi di validazione, uso sostitutivo del referto originale |

## Separazione funzionale

- **Amministrazione e infrastruttura informativa.** Identità, booking, pagamenti, catalogo farmacia, conservazione e condivisione senza elaborazione decisionale. Qualificazione da riesaminare se viene introdotta una finalità medica o se diventano parte di una funzione clinica di sicurezza.
- **Funzioni candidate a dispositivo.** Interpretazione o prioritizzazione di risultati individuali, confronto clinico di intervalli e flag, alert, suggerimenti su farmaci, imaging AI e monitoraggio con soglie. L'analisi considera anche il danno da output mancante, mal classificato o in ritardo.
- **Ricerca.** Export soggetti a finalità, consenso, regole di disclosure e revisione. Il catalogo di ricerca rimane separato dalla revisione del singolo paziente.

Le dichiarazioni future di marketing, interfaccia, IFU e formazione devono mantenere lo stesso perimetro. L'estensione a minori, urgenze, nuove popolazioni o autonomia decisionale riapre classificazione, hazard, evidenze e approvazioni.
