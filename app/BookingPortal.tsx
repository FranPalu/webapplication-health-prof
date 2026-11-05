'use client';

import {useState, type FormEvent} from 'react';
import {api} from '../lib/api/client';
import type {components} from '../lib/api/schema';

type Page<T> = {results: T[]; next: string | null};
type Slot = components['schemas']['SlotOutput'];
type Booking = components['schemas']['BookingOutput'];
type Item = components['schemas']['ItemOutput'];
type Reservation = components['schemas']['ReservationOutput'];
type Place = {id: string; name: string; kind: string; distance_m: number};

export function BookingPortal({organizations, english}: {organizations: string[]; english: boolean}) {
  const [org, setOrg] = useState('');
  const [slots, setSlots] = useState<Slot[]>([]);
  const [bookings, setBookings] = useState<Booking[]>([]);
  const [items, setItems] = useState<Item[]>([]);
  const [places, setPlaces] = useState<Place[]>([]);
  const [reservations, setReservations] = useState<Reservation[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const t = (it: string, en: string) => english ? en : it;
  const date = (value: string) => new Date(value).toLocaleString(english ? 'en' : 'it', {timeZone:'Europe/Rome'});
  const stateLabel = (state: string) => ({
    pending: t('In attesa', 'Pending'), confirmed: t('Confermata', 'Confirmed'), rejected: t('Rifiutata', 'Rejected'),
  }[state] ?? state);

  async function run(work: () => Promise<void>) {
    setBusy(true);
    setMessage('');
    try {await work();}
    catch {setMessage(t('Operazione non disponibile. Aggiorna la disponibilità e riprova.', 'Action unavailable. Refresh availability and retry.'));}
    finally {setBusy(false);}
  }

  async function loadSlots(id: string) {
    setSlots(id ? (await api<Page<Slot>>('organizations/' + id + '/appointment-slots/')).results : []);
  }

  async function loadBookings() {
    setBookings((await api<Page<Booking>>('appointments/bookings/')).results);
  }

  function nearby(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const query = new URLSearchParams();
    for (const key of ['latitude', 'longitude', 'radius_km']) query.set(key, String(fields.get(key)));
    void run(async () => setPlaces(await api<Place[]>('directory/nearby/?' + query)));
  }

  async function loadCatalog(id: string) {
    setItems((await api<Page<Item>>('organizations/' + id + '/pharmacy/catalog/')).results);
  }

  async function loadReservations() {
    setReservations((await api<Page<Reservation>>('pharmacy/reservations/')).results);
  }

  return <section className="identity-card">
    <h2>{t('Prenotazioni e farmacia', 'Appointments and pharmacies')}</h2>
    {message && <p role="status">{message}</p>}
    <fieldset disabled={busy}>
      <legend>{t('Appuntamenti', 'Appointments')}</legend>
      <label>{t('Struttura collegata', 'Linked organization')}<select value={org} onChange={event => {
        setOrg(event.target.value);
        setSlots([]);
      }}>
        <option value="">—</option>
        {organizations.map(id => <option key={id} value={id}>{id}</option>)}
      </select></label>
      <button type="button" onClick={() => void run(async () => {await loadSlots(org); await loadBookings();})}>
        {t('Aggiorna disponibilità e prenotazioni', 'Refresh slots and bookings')}
      </button>
      <ul>{slots.map(slot => <li key={slot.id}>
        {slot.title} · {date(slot.starts_at)}
        <form onSubmit={event => {
          event.preventDefault();
          const payment = new FormData(event.currentTarget).get('payment');
          void run(async () => {
            await api('appointments/slots/' + slot.id + '/book/', payment ? {payment} : {});
            await loadSlots(org);
            await loadBookings();
          });
        }}>
          {slot.price && <label>{t('ID pagamento simulato, facoltativo', 'Simulated payment ID, optional')}<input name="payment"/></label>}
          <button>{t('Prenota', 'Book')}</button>
        </form>
      </li>)}</ul>
      <ul>{bookings.map(booking => <li key={booking.id}>
        {booking.title} · {date(booking.starts_at)}
        {booking.cancelled_at ? t(' · Annullato', ' · Cancelled') : <>
          <button type="button" onClick={() => {
            if (!window.confirm(t('Annullare l’appuntamento?', 'Cancel the appointment?'))) return;
            void run(async () => {
              await api('appointments/bookings/' + booking.id + '/cancel/', {});
              await loadBookings();
              await loadSlots(org);
            });
          }}>{t('Annulla', 'Cancel')}</button>
          {!!slots.length && <form onSubmit={event => {
            event.preventDefault();
            const slot = new FormData(event.currentTarget).get('slot');
            void run(async () => {
              await api('appointments/bookings/' + booking.id + '/reschedule/', {slot});
              await loadBookings();
              await loadSlots(org);
            });
          }}>
            <label>{t('Nuova fascia', 'New slot')}<select name="slot" required>
              <option value="">—</option>
              {slots.map(slot => <option key={slot.id} value={slot.id}>{slot.title} · {date(slot.starts_at)}</option>)}
            </select></label>
            <button>{t('Riprogramma', 'Reschedule')}</button>
          </form>}
        </>}
      </li>)}</ul>
    </fieldset>
    <fieldset disabled={busy}>
      <legend>{t('Cerca nelle vicinanze', 'Find nearby')}</legend>
      <form onSubmit={nearby}>
        <label>{t('Latitudine', 'Latitude')}<input name="latitude" type="number" step="0.000001" min="-90" max="90" required/></label>
        <label>{t('Longitudine', 'Longitude')}<input name="longitude" type="number" step="0.000001" min="-180" max="180" required/></label>
        <label>{t('Raggio in km', 'Radius in km')}<input name="radius_km" type="number" min="1" max="50" defaultValue="10" required/></label>
        <button>{t('Cerca', 'Search')}</button>
      </form>
      <ul>{places.map(place => <li key={place.id}>{place.name} · {place.distance_m} m
        {place.kind === 'pharmacy' && <button type="button" onClick={() => void run(() => loadCatalog(place.id))}>
          {t('Apri catalogo', 'Open catalog')}
        </button>}
      </li>)}</ul>
      <ul>{items.map(item => <li key={item.id}>{item.title}
        {item.prescription_required ? t(' · Richiede verifica della ricetta', ' · Prescription verification required')
          : item.available && <button type="button" onClick={() => void run(async () => {
            await api('pharmacy/items/' + item.id + '/reserve/', {request_id: crypto.randomUUID(), quantity: 1});
            await loadReservations();
          })}>{t('Riserva una unità', 'Reserve one unit')}</button>}
      </li>)}</ul>
      <button type="button" onClick={() => void run(loadReservations)}>{t('Aggiorna richieste farmacia', 'Refresh pharmacy reservations')}</button>
      <ul>{reservations.map(row => <li key={row.id}>{row.id} · {stateLabel(row.state ?? '')}</li>)}</ul>
    </fieldset>
  </section>;
}

export function BookingAdministration({organization, pharmacy, english}: {
  organization: string; pharmacy: boolean; english: boolean;
}) {
  const [pending, setPending] = useState<Reservation[]>([]);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const t = (it: string, en: string) => english ? en : it;
  const base = 'organizations/' + organization + '/';
  async function run(action: () => Promise<void>) {
    setBusy(true);
    try {await action(); setMessage(t('Operazione completata.', 'Action completed.'));}
    catch {setMessage(t('Operazione non riuscita. Controlla dati e permessi.', 'Action failed. Check values and permissions.'));}
    finally {setBusy(false);}
  }
  async function queue() {
    setPending((await api<Page<Reservation>>(base + 'pharmacy/reservations/')).results);
  }
  function submit(event: FormEvent<HTMLFormElement>, path: string) {
    event.preventDefault();
    const fields = new FormData(event.currentTarget);
    const body = Object.fromEntries(fields);
    if (!body.price) delete body.price;
    void run(async () => {
      await api(base + path, path === 'pharmacy/catalog/'
        ? {...body, stock: Number(body.stock), prescription_required: fields.has('prescription_required')}
        : body);
    });
  }
  return <details>
    <summary>{t('Gestione disponibilità e posizione', 'Manage availability and location')}</summary>
    {message && <p role="status">{message}</p>}
    <fieldset disabled={busy}>
      <form onSubmit={event => submit(event, 'location/')}>
        <label>{t('Latitudine', 'Latitude')}<input name="latitude" type="number" step="0.000001" required/></label>
        <label>{t('Longitudine', 'Longitude')}<input name="longitude" type="number" step="0.000001" required/></label>
        <button>{t('Pubblica posizione della struttura', 'Publish organization location')}</button>
      </form>
      {pharmacy ? <>
        <form onSubmit={event => submit(event, 'pharmacy/catalog/')}>
          <label>SKU<input name="sku" maxLength={64} required/></label>
          <label>{t('Prodotto', 'Item')}<input name="title" maxLength={120} required/></label>
          <label>{t('Unità disponibili', 'Available units')}<input name="stock" type="number" min="0" max="100000" required/></label>
          <label><input name="prescription_required" type="checkbox" defaultChecked/>{t('Ricetta richiesta', 'Prescription required')}</label>
          <button>{t('Salva prodotto', 'Save item')}</button>
        </form>
        <button type="button" onClick={() => void run(queue)}>{t('Aggiorna coda farmacia', 'Refresh pharmacy queue')}</button>
        <ul>{pending.map(row => <li key={row.id}>{row.item} · {row.quantity}
          {(['confirmed', 'rejected'] as const).map(decision => <button key={decision} type="button" onClick={() => void run(async () => {
            await api('pharmacy/reservations/' + row.id + '/decision/', {decision});
            await queue();
          })}>{decision === 'confirmed' ? t('Conferma', 'Confirm') : t('Rifiuta', 'Reject')}</button>)}
        </li>)}</ul>
      </> : <form onSubmit={event => submit(event, 'appointment-slots/')}>
        <label>{t('Titolo fascia', 'Slot title')}<input name="title" maxLength={120} required/></label>
        <label>{t('ID professionista', 'Professional ID')}<input name="professional" required/></label>
        <label>{t('Inizio ISO 8601 con offset', 'Start ISO 8601 with offset')}<input name="starts_at" placeholder="2027-01-25T14:00:00+01:00" required/></label>
        <label>{t('Fine ISO 8601 con offset', 'End ISO 8601 with offset')}<input name="ends_at" placeholder="2027-01-25T14:30:00+01:00" required/></label>
        <label>{t('ID prezzo facoltativo', 'Optional price ID')}<input name="price"/></label>
        <button>{t('Pubblica fascia', 'Publish slot')}</button>
      </form>}
    </fieldset>
  </details>;
}
