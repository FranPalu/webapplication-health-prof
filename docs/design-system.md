# Design system Clarìa

Palette bianco/viola in Light mode, grigio scuro/viola in Dark mode. Il tema è condiviso fra login, anteprime e gestionale.

Il gestionale usa le coppie --surface/--ink e --lavender/--sage-ink. Testi secondari: --muted. Successi, avvisi ed errori hanno ciascuno una coppia di token per sfondo e testo. Non usare colori fissi chiari su componenti che cambiano tema.

Campi alti almeno 44 px, testo dei moduli e delle tabelle a 14 px, metadati a 12 px. Finestre con intestazione e azioni aderenti al tema; focus visibile viola. Le informazioni tecniche facoltative vanno in sezioni espandibili.

Playwright misura un contrasto minimo 4.5:1 su titoli, etichette, aiuti, campi e pulsanti del modulo paziente in entrambi i temi. Questo controllo non costituisce una verifica completa WCAG dell'applicazione.

## Portale autenticato M8

La dashboard usa il ruolo assegnato all'account restituito dalla sessione.
Con una sola organizzazione, il portale la apre come contesto iniziale.
L'utente può scegliere il tipo di account alla registrazione. Le singole
dashboard dimostrative mostrano un solo profilo. Il selettore della demo
si trova nella galleria pubblica.

Il riepilogo usa le superfici del tema e i colori di accento già condivisi con login e demo. Le azioni principali dipendono dal profilo attivo. Farmacia si seleziona dall'organizzazione, mentre l'amministratore di piattaforma ha collegamenti alle verifiche e alle approvazioni. I contatori descrivono gli elementi caricati nella pagina e le notifiche non lette ricevute. Non rappresentano totali di sistema.

Gli accessi rapidi sono link nativi con destinazioni focalizzabili. Il salto al contenuto è il primo elemento raggiungibile a tastiera e conserva il frammento usato per i token di verifica. Campi, aree di testo e pulsanti rispettano il tema attivo. Gli esiti del portale usano una sola regione di stato e gli errori API vengono presentati in forma leggibile.

Il manifest espone avvio, modalità standalone e icone pubbliche. Non viene registrato un service worker. La consultazione clinica richiede una connessione e il backend mantiene Cache-Control no-store per i dati protetti.

I test Playwright verificano il salto al contenuto, il manifest e i riepiloghi dei sei profili. Per ciascun profilo controllano l'albero di accessibilità della navigazione, il focus sulla destinazione, il layout a 320 px nei due temi e il cambio di lingua. Questi scenari usano risposte API sintetiche.

I collaudi con Django e dati fittizi verificano una funzione principale per ruolo. Il paziente concede e revoca il consenso alla ricerca. Il professionista carica, cerca, scarica e archivia un documento. L'amministratore di struttura pubblica la posizione, la farmacia aggiunge un prodotto, il ricercatore invia una richiesta di accesso e l'amministratore di piattaforma apre la coda delle richieste. Il test del ricercatore verifica anche il cambio di lingua dello stato della richiesta.

Per il collaudo manuale usare profili sintetici e un lettore di schermo nativo. Percorrere accesso, riepilogo, azioni rapide e operazione principale di ogni ruolo, in IT e EN. Verificare gli annunci di intestazioni, campi, errori e conferme, il focus dopo ogni azione e la lettura delle tabelle. Registrare combinazione di browser e lettore, esito e criteri applicabili. Restano aperti questo collaudo e la verifica completa delle traduzioni dei singoli moduli. [WCAG 2.2](https://www.w3.org/TR/WCAG22/)

Su macOS, Comando–F5 attiva o disattiva VoiceOver. Per raccogliere gli annunci
durante la prova si può mostrare il pannello dei sottotitoli con
VO–Fn–Comando–F10. [Comandi VoiceOver per Mac](https://support.apple.com/guide/voiceover/general-commands-cpvokys01/mac)
