# M6 — Prima consegna

## Appuntamenti

- POST /api/v1/organizations/{id}/appointment-slots/ pubblica una fascia con title, professional, starts_at, ends_at e price facoltativo. Serve un amministratore del tenant con MFA. Il professionista deve essere verificato e membro attivo. Le fasce sovrapposte sono rifiutate anche tra strutture.
- GET sullo stesso percorso mostra le fasce future libere ai pazienti collegati alla struttura. Inviare timestamp ISO 8601 con offset esplicito. Il backend confronta gli istanti, anche quando cambia l'offset locale.
- POST /api/v1/appointments/slots/{id}/book/ prenota la fascia. Il corpo vuoto lascia il pagamento in loco. Il campo payment collega un ordine simulato pagato dello stesso utente e dello stesso prezzo. Un ordine può essere collegato una sola volta.
- GET /api/v1/appointments/bookings/ elenca le prenotazioni dell'utente. POST /api/v1/appointments/bookings/{id}/cancel/ annulla prima dell'inizio e registra l'eventuale rimborso simulato nella stessa transazione.

## Farmacia

- GET e POST /api/v1/organizations/{id}/pharmacy/catalog/ leggono e aggiornano il catalogo. POST richiede un amministratore della farmacia con MFA e accetta sku, title, stock e prescription_required. Stock indica le unità disponibili, escluse quelle già riservate.
- POST /api/v1/pharmacy/items/{id}/reserve/ riserva quantity unità con request_id univoco per utente. La stessa richiesta non scala due volte le scorte.
- GET /api/v1/pharmacy/reservations/ mostra le richieste del paziente. GET /api/v1/organizations/{id}/pharmacy/reservations/ mostra la coda della farmacia. POST /api/v1/pharmacy/reservations/{id}/decision/ accetta confirmed o rejected. Il rifiuto ripristina le unità. Entrambi gli esiti producono una notifica nell'app.
- Le richieste per prodotti con obbligo di prescrizione sono bloccate fino alla verifica del riferimento. Questa consegna non raccoglie NRE, allegati o dati di ricetta.

Restano da completare interfaccia portale, riprogrammazione, reminder email/SMS, migrazione agenda, import CSV, gestione e verifica dei riferimenti di ricetta e ricerca geografica.
