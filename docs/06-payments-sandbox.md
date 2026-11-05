# M5 — Prima consegna Stripe Connect

Checkout è disponibile in DEBUG con chiave Stripe di test e segreto webhook. Impostare le variabili in .env.dev. STRIPE_TEST_DESTINATIONS contiene una mappa JSON da UUID dell'organizzazione ad account Connect di test. Il portale ritorna a PUBLIC_ORIGIN dopo Checkout. L'API invia a Stripe importo, commissione, destinazione e un riferimento casuale all'ordine. Il nome del servizio clinico resta nell'applicazione.

- Un amministratore dell'organizzazione con MFA crea un prezzo EUR con POST /api/v1/organizations/{id}/payment-prices/. Il corpo contiene title, amount e fee in centesimi. Gli account paziente collegati possono leggere il listino.
- Un paziente collegato apre Checkout con POST /api/v1/payments/checkout/ e invia price e request_id. Riutilizzare lo stesso request_id dopo un errore di rete. Importo e commissione vengono copiati dal listino. Il retry è limitato a 23 ore dalla creazione.
- Configurare Stripe CLI per inoltrare gli eventi snapshot checkout.session.completed e checkout.session.async_payment_succeeded a /api/v1/payments/stripe/webhook/. L'ordine è pagato solo dopo un evento firmato che corrisponde a sessione, importo e valuta. Il ritorno dal browser non cambia lo stato.
- GET /api/v1/payments/orders/ mostra gli ordini del pagante.

Il test locale usa un provider simulato e verifica firme, replay, isolamento e importi. La prova dal vivo richiede un account Stripe Connect di test. Restano da implementare interfaccia nel portale, rimborsi, fatture e ricevute, imposte, riconciliazione periodica, import legacy e adapter SDI. Nessuna emissione fiscale è associata allo stato pagato.

Fonti: [Destination charges](https://docs.stripe.com/connect/destination-charges), [webhook Stripe](https://docs.stripe.com/webhooks).
