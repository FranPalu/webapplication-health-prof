# M6 — Prenotazioni e farmacia

## Appuntamenti

- POST /api/v1/organizations/{id}/appointment-slots/ pubblica una fascia con title, professional, starts_at, ends_at e price facoltativo. Serve un amministratore del tenant con MFA. Il professionista deve essere verificato e membro attivo. Le fasce sovrapposte sono rifiutate anche tra strutture.
- GET sullo stesso percorso mostra le fasce future libere ai pazienti collegati alla struttura. Inviare timestamp ISO 8601 con offset esplicito. Il backend confronta gli istanti, anche quando cambia l'offset locale.
- POST /api/v1/appointments/slots/{id}/book/ prenota la fascia. Il corpo vuoto lascia il pagamento in loco. Il campo payment collega un ordine simulato pagato dello stesso utente e dello stesso prezzo. Un ordine può essere collegato una sola volta.
- GET /api/v1/appointments/bookings/ elenca le prenotazioni dell'utente. POST /api/v1/appointments/bookings/{id}/cancel/ annulla prima dell'inizio e registra l'eventuale rimborso simulato nella stessa transazione.

## Farmacia

- GET e POST /api/v1/organizations/{id}/pharmacy/catalog/ leggono e aggiornano il catalogo. POST richiede un amministratore della farmacia con MFA e accetta sku, title, stock e prescription_required. Stock indica le unità disponibili, escluse quelle già riservate.
- POST /api/v1/pharmacy/items/{id}/reserve/ riserva quantity unità con request_id univoco per utente. La stessa richiesta non scala due volte le scorte.
- GET /api/v1/pharmacy/reservations/ mostra le richieste del paziente. GET /api/v1/organizations/{id}/pharmacy/reservations/ mostra la coda della farmacia. POST /api/v1/pharmacy/reservations/{id}/decision/ accetta confirmed o rejected. Il rifiuto ripristina le unità. Entrambi gli esiti producono una notifica nell'app.
- Le richieste per prodotti con obbligo di prescrizione sono bloccate fino alla verifica del riferimento. La configurazione standard non raccoglie dati di ricetta.

## Completamento M6

- Il paziente usa **Prenotazioni e farmacia** per vedere le fasce disponibili, prenotare, spostare o annullare. La riprogrammazione conserva la stessa prenotazione e l'eventuale pagamento, richiede stessa struttura e prezzo, e libera la fascia originaria. Il portale visualizza gli orari in Europe/Rome e l'API richiede un offset esplicito.
- Gli amministratori pubblicano posizione, disponibilità e catalogo e gestiscono la coda farmacia dal portale. La directory PostGIS cerca entro 1–50 km dalle coordinate indicate. Vengono pubblicate solo le sedi che hanno configurato la posizione.
- Celery controlla ogni minuto gli appuntamenti nelle prossime 24 ore. Crea una notifica e tenta un'email generica dopo il commit. Una riprogrammazione azzera il marcatore. L'adapter SMS resta disattivato e deve verificare opt-in e idempotenza se collegato.
- `python manage.py import_pharmacy_catalog UUID farmacia.csv` valida un CSV con sku, title, stock e prescription_required. Mostra numeri di riga e campi invalidi. `--apply` scrive atomicamente.
- `python manage.py import_legacy_appointments agenda.json` valida una lista di appuntamenti con source, owner, legacy_id, patient_legacy_id, organization, professional, state, title, starts_at ed ends_at. Richiede state booked e un paziente già collegato. Non importa pagamenti o appuntamenti annullati. `--apply` scrive; la stessa mappatura è ripetibile.
- L'API farmacia può accettare un NRE cifrato quando è collegato un adapter autorizzato. Il riferimento è verificato prima della conferma e rimosso dopo la decisione. La configurazione standard lascia bloccati gli articoli soggetti a prescrizione. Il caricamento di allegati e la validazione presso i sistemi ufficiali richiedono una successiva integrazione.
