# Design system Clarìa

Palette bianco/viola in Light mode, grigio scuro/viola in Dark mode. Il tema è condiviso fra login, anteprime e gestionale.

Il gestionale usa le coppie --surface/--ink e --lavender/--sage-ink. Testi secondari: --muted. Successi, avvisi ed errori hanno ciascuno una coppia di token per sfondo e testo. Non usare colori fissi chiari su componenti che cambiano tema.

Campi alti almeno 44 px, testo dei moduli e delle tabelle a 14 px, metadati a 12 px. Finestre con intestazione e azioni aderenti al tema; focus visibile viola. Le informazioni tecniche facoltative vanno in sezioni espandibili.

Playwright misura un contrasto minimo 4.5:1 su titoli, etichette, aiuti, campi e pulsanti del modulo paziente in entrambi i temi. Questo controllo non costituisce una verifica completa WCAG dell'applicazione.

## Portale autenticato M8

Il riepilogo usa le superfici del tema e i colori di accento già condivisi con login e demo. Le azioni principali dipendono dal profilo attivo. Farmacia si seleziona dall'organizzazione, mentre l'amministratore di piattaforma ha collegamenti alle verifiche e alle approvazioni. I contatori descrivono gli elementi caricati nella pagina e le notifiche non lette ricevute. Non rappresentano totali di sistema.

Gli accessi rapidi sono link nativi con destinazioni focalizzabili. Il salto al contenuto è il primo elemento raggiungibile a tastiera e conserva il frammento usato per i token di verifica. Campi, aree di testo e pulsanti rispettano il tema attivo. Gli esiti del portale usano una sola regione di stato e gli errori API vengono presentati in forma leggibile.

Il manifest espone avvio, modalità standalone e icone pubbliche. Non viene registrato un service worker. La consultazione clinica richiede una connessione e il backend mantiene Cache-Control no-store per i dati protetti.

I test di regressione coprono il salto al contenuto, l'accesso agli appuntamenti da tastiera, il layout mobile nei due temi, le etichette IT/EN e il manifest. Restano da completare l'audit con lettori di schermo, la verifica dei flussi per tutti i ruoli e la revisione delle traduzioni di ciascun modulo.
