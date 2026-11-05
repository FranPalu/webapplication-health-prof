# Design system Clarìa

Palette bianco/viola in Light mode, grigio scuro/viola in Dark mode. Il tema è condiviso fra login, anteprime e gestionale.

Il gestionale usa le coppie --surface/--ink e --lavender/--sage-ink. Testi secondari: --muted. Successi, avvisi ed errori hanno ciascuno una coppia di token per sfondo e testo. Non usare colori fissi chiari su componenti che cambiano tema.

Campi alti almeno 44 px, testo dei moduli e delle tabelle a 14 px, metadati a 12 px. Finestre con intestazione e azioni aderenti al tema; focus visibile viola. Le informazioni tecniche facoltative vanno in sezioni espandibili.

Playwright misura un contrasto minimo 4.5:1 su titoli, etichette, aiuti, campi e pulsanti del modulo paziente in entrambi i temi. Questo controllo non costituisce una verifica completa WCAG dell'applicazione.

## Portale autenticato M8

Il riepilogo usa le superfici del tema e i colori di accento già condivisi con login e demo. Le azioni principali dipendono dal profilo attivo. Farmacia si seleziona dall'organizzazione, mentre l'amministratore di piattaforma ha collegamenti alle verifiche e alle approvazioni. I contatori descrivono gli elementi caricati nella pagina e le notifiche non lette ricevute. Non rappresentano totali di sistema.

Gli accessi rapidi sono link nativi con destinazioni focalizzabili. Il salto al contenuto è il primo elemento raggiungibile a tastiera e conserva il frammento usato per i token di verifica. Campi, aree di testo e pulsanti rispettano il tema attivo. Gli esiti del portale usano una sola regione di stato e gli errori API vengono presentati in forma leggibile.

Il manifest espone avvio, modalità standalone e icone pubbliche. Non viene registrato un service worker. La consultazione clinica richiede una connessione e il backend mantiene Cache-Control no-store per i dati protetti.

I test Playwright verificano il salto al contenuto, il manifest e i riepiloghi dei sei profili. Per ciascun profilo controllano l'albero di accessibilità della navigazione, il focus sul collegamento di destinazione, il layout a 320 px nei due temi e il passaggio delle etichette e della lingua del documento da italiano a inglese. Questi scenari usano risposte API sintetiche. Registrazione, MFA, documenti e consenso alla ricerca hanno scenari separati sul backend locale.

Per il collaudo manuale usare profili sintetici e un lettore di schermo nativo. Percorrere accesso, riepilogo, azioni rapide e operazione principale di ogni ruolo, in IT e EN. Verificare gli annunci di intestazioni, campi, errori e conferme, il focus dopo ogni azione e la lettura delle tabelle. Registrare combinazione di browser e lettore, esito e criteri applicabili. Restano aperti questo collaudo, la verifica end-to-end di tutti i ruoli e il controllo completo delle traduzioni dei moduli. [WCAG 2.2](https://www.w3.org/TR/WCAG22/)
