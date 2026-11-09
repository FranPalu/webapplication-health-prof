'use client';

import {useState, type FormEvent} from 'react';
import {ClinicalAnalysis} from './ClinicalAnalysis';
import {api} from '../lib/api/client';
import type {components} from '../lib/api/schema';

type Version = components['schemas']['VersionOutput'];
type Page<T = Version> = {results: T[]; next: string | null};
type Folder = components['schemas']['FolderOutput'];

export function ClinicalDocuments({patient, write, english, shareChanged, organization}: {
  patient: string; write: boolean; english: boolean; organization?: string; shareChanged?: () => Promise<void>;
}) {
  const [page, setPage] = useState<Page | null>(null);
  const [folders, setFolders] = useState<Folder[]>([]);
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('other');
  const [identityRecorded, setIdentityRecorded] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<Version | null>(null);
  const [history, setHistory] = useState<Page | null>(null);
  const path = 'clinical/patients/' + patient + '/documents/';
  const foldersPath = 'clinical/patients/' + patient + '/folders/';
  const label = (it: string, en: string) => english ? en : it;
  const selectedPath = selected ? 'clinical/documents/' + selected.document + '/' : '';

  async function perform(action: () => Promise<void>) {
    setBusy(true);
    setError('');
    try { await action(); }
    catch { setError(label('Operazione non riuscita. Verifica il file, i permessi e riprova.', 'Action failed. Check the file and your permissions, then retry.')); }
    finally { setBusy(false); }
  }

  async function load() {
    setPage(await api<Page>(path + '?q=' + encodeURIComponent(query)));
  }

  async function loadFolders() {
    const all: Folder[] = [];
    let path = foldersPath;
    while (path) {
      const page = await api<Page<Folder>>(path);
      all.push(...page.results);
      path = page.next ? foldersPath + new URL(page.next, window.location.origin).search : '';
    }
    setFolders(all);
  }

  function createFolder(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    void perform(async () => {
      const parent = data.get('parent');
      await api(foldersPath, {title: data.get('title'), ...(parent ? {parent_folder: parent} : {})});
      form.reset();
      await loadFolders();
    });
  }

  function enrollIdentifier(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    setIdentityRecorded(false);
    void perform(async () => {
      await api('clinical/patients/' + patient + '/identifiers/', Object.fromEntries(fields));
      form.reset();
      setIdentityRecorded(true);
    });
  }

  function sourceFields() {
    return <>
      <label>{label('Tipo di identificativo', 'Identifier type')}<select name="identifier_kind">
        <option value="facility">{label('Identificativo di struttura', 'Facility identifier')}</option>
        <option value="tax_code">{label('Codice fiscale', 'Italian tax code')}</option>
        <option value="health_card">{label('Numero tessera sanitaria', 'Health card number')}</option>
      </select></label>
      <label>{label('Identificativo dalla fonte', 'Identifier from source')}<input name="identifier_value" maxLength={64} autoComplete="off" required/></label>
      <label>{label('Data di nascita dalla fonte', 'Date of birth from source')}<input name="source_birth_date" type="date" autoComplete="off" required/></label>
    </>;
  }

  function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const payload = new FormData(form);
    if (!payload.get('folder')) payload.delete('folder');
    void perform(async () => {
      await api(selectedPath || path, payload);
      form.reset();
      setKind('other');
      setSelected(null);
      setHistory(null);
      await load();
    });
  }

  function requestShare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const fields = new FormData(form);
    if (!selected) return;
    void perform(async () => {
      const recipient = fields.get('recipient');
      const folder = fields.get('folder');
      const target = fields.get('organization') ? {recipient_organization: recipient} : {recipient_user: recipient};
      await api('shares/', {
        patient, ...(folder ? {folder, scope: 'folder'} : {document: selected.document, scope: 'item'}),
        ...target, purpose: fields.get('purpose'),
        permissions: fields.get('download') ? ['view', 'download'] : ['view'],
      });
      form.reset();
      await shareChanged?.();
    });
  }

  return <details>
    <summary>{label('Documenti clinici', 'Clinical documents')}</summary>
    <form onSubmit={event => {event.preventDefault(); void perform(load);}}>
      <label>{label('Cerca nei documenti', 'Search documents')}<input maxLength={160} value={query} onChange={event => setQuery(event.target.value)}/></label>
      <button disabled={busy}>{label('Cerca o mostra tutti', 'Search or show all')}</button>
    </form>
    {write && <details onToggle={event => {
      if (event.currentTarget.open) void perform(loadFolders);
    }}>
      <summary>{label('Gestisci cartelle', 'Manage folders')}</summary>
      <form onSubmit={createFolder}>
        <label>{label('Nome cartella', 'Folder name')}<input name="title" maxLength={100} required/></label>
        <label>{label('Cartella superiore', 'Parent folder')}<select name="parent">
          <option value="">{label('Nessuna', 'None')}</option>
          {folders.map(folder => <option key={folder.id} value={folder.id}>{folder.title}</option>)}
        </select></label>
        <button disabled={busy}>{label('Crea cartella', 'Create folder')}</button>
      </form>
    </details>}
    {write && <details>
      <summary>{label('Registra identificativo da una fonte verificata', 'Record an identifier from a verified source')}</summary>
      <form onSubmit={enrollIdentifier}>
        <p>{label('Verifica il paziente e i dati presso la fonte prima di registrare.', 'Verify the patient and details against the source before recording.')}</p>
        {sourceFields()}
        <button disabled={busy}>{label('Registra identificativo', 'Record identifier')}</button>
      </form>
      {identityRecorded && <p role="status">{label('Identificativo registrato.', 'Identifier recorded.')}</p>}
    </details>}
    {error && <p role="alert">{error}</p>}
    {page && !page.results.length && <p>{label('Nessun documento trovato.', 'No documents found.')}</p>}
    <ul>{page?.results.map(version => <li key={version.id}>
      <button disabled={busy} onClick={() => void perform(async () => {
        setHistory(await api<Page>('clinical/documents/' + version.document + '/'));
        setSelected(version);
      })}>{version.title} · v{version.number}</button>
    </li>)}</ul>
    {page?.next && <button disabled={busy} onClick={() => void perform(async () => {
      const next = await api<Page>(path + new URL(page.next!, window.location.origin).search);
      setPage({results: [...page.results, ...next.results], next: next.next});
    })}>{label('Carica altri', 'Load more')}</button>}
    {selected && <>
      <h4>{selected.title}</h4>
      <button onClick={() => {setSelected(null); setHistory(null);}}>{label('Chiudi storico', 'Close history')}</button>
      <ul>{history?.results.map(version => <li key={version.id}>
        {version.can_download
          ? <a href={'/api/v1/clinical/versions/' + version.id + '/download/'}>{label('Scarica versione', 'Download version')} {version.number}</a>
          : <span>{label('Versione', 'Version')} {version.number}</span>}
        {version.kind === 'prescription' && <p>{label('ID versione ricetta', 'Prescription version ID')}: <code>{version.id}</code></p>}
        {write && version.can_analyze && <ClinicalAnalysis version={version.id} english={english} organization={organization}/>}
      </li>)}</ul>
      {history?.next && <button disabled={busy} onClick={() => void perform(async () => {
        const next = await api<Page>(selectedPath + new URL(history.next!, window.location.origin).search);
        setHistory({results: [...history.results, ...next.results], next: next.next});
      })}>{label('Carica altre versioni', 'Load more versions')}</button>}
      {selected.can_share && <form onSubmit={requestShare}>
        <label>{label('ID destinatario', 'Recipient ID')}<input name="recipient" required/></label>
        <label><input name="organization" type="checkbox"/>{label('Il destinatario è un’organizzazione', 'Recipient is an organization')}</label>
        {selected.folder && <label><input name="folder" type="checkbox" value={selected.folder}/>{label('Condividi la cartella e le sottocartelle', 'Share the folder and its subfolders')}</label>}
        <label>{label('Finalità', 'Purpose')}<input name="purpose" maxLength={300} required/></label>
        <label><input name="download" type="checkbox"/>{label('Consenti il download', 'Allow download')}</label>
        <button disabled={busy}>{label('Richiedi consenso alla condivisione', 'Request sharing consent')}</button>
      </form>}
    </>}
    {write && (!selected || selected.can_edit) && <form onSubmit={upload}>
      <label>{label('Titolo del documento', 'Document title')}<input name="title" maxLength={160} required/></label>
      {!selected && <label>{label('Categoria', 'Category')}<select name="kind" value={kind} onChange={event => setKind(event.target.value)}>
        <option value="other">{label('Altro', 'Other')}</option>
        <option value="prescription">{label('Ricetta', 'Prescription')}</option>
        <option value="report">{label('Referto', 'Report')}</option>
        <option value="nutrition">{label('Piano alimentare', 'Nutrition plan')}</option>
        <option value="psychology">{label('Nota psicologica riservata', 'Restricted psychology note')}</option>
      </select></label>}
      {!selected && folders.length > 0 && <label>{label('Cartella', 'Folder')}<select name="folder">
        <option value="">{label('Nessuna', 'None')}</option>
        {folders.map(folder => <option key={folder.id} value={folder.id}>{folder.title}</option>)}
      </select></label>}
      {(selected?.kind ?? kind) === 'report' && <fieldset>
        <legend>{label('Conferma il paziente indicato nel referto', 'Confirm the patient identified on the report')}</legend>
        {sourceFields()}
      </fieldset>}
      <label>{label('File (massimo 10 MiB)', 'File (maximum 10 MiB)')}<input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.dcm" required/></label>
      <button disabled={busy}>{selected ? label('Carica nuova versione', 'Upload new version') : label('Carica documento', 'Upload document')}</button>
      {selected && <button type="button" disabled={busy} onClick={() => {
        if (!window.confirm(label('Archiviare tutte le versioni del documento?', 'Archive all versions of this document?'))) return;
        void perform(async () => {await api(selectedPath, undefined, 'DELETE'); setSelected(null); setHistory(null); await load();});
      }}>{label('Archivia documento', 'Archive document')}</button>}
    </form>}
  </details>;
}
