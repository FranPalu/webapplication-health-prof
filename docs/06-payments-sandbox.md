# M5 — Simulazione interna

La simulazione usa PostgreSQL e le sessioni Clarìa. Non richiede credenziali, carte, redirect o webhook. Tutti gli importi sono in centesimi di euro. Lo stato non prova un incasso e non genera documenti fiscali.

- Un amministratore con MFA crea un prezzo con POST /api/v1/organizations/{id}/payment-prices/. Gli account paziente collegati possono leggere il listino.
- POST /api/v1/payments/checkout/ accetta price, request_id e outcome tra paid, declined e cancelled. Importo e commissione derivano dal listino. Ripetere lo stesso request_id restituisce lo stesso ordine. Un esito diverso con lo stesso identificativo restituisce 409.
- GET /api/v1/payments/orders/ mostra gli ordini del pagante e il campo simulation_status. Gli ordini precedenti mantengono lo stato legacy.
- POST /api/v1/payments/orders/{id}/refund/ permette all'amministratore con MFA del tenant di simulare un rimborso integrale. Ripetere l'operazione non produce un secondo rimborso.

Il flusso è disponibile via API. L'interfaccia nel portale, i documenti contabili e l'integrazione reale restano attività separate.
