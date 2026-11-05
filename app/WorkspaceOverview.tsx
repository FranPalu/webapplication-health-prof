import {
  ArrowUpRight, Bell, Building2, CalendarDays, ClipboardList, FlaskConical,
  FolderHeart, ShieldCheck, UsersRound,
} from 'lucide-react';

type Profile = 'patient' | 'professional' | 'organization_admin' | 'researcher';
type Workspace = Profile | 'pharmacy' | 'platform';

export function WorkspaceOverview({role, platform, selectedKind, english, patients, organizations, notifications}: {
  role: Profile;
  platform: boolean;
  selectedKind?: string;
  english: boolean;
  patients: number;
  organizations: number;
  notifications: number;
}) {
  const t = (it: string, en: string) => english ? en : it;
  const workspace: Workspace = platform ? 'platform'
    : role === 'organization_admin' && selectedKind === 'pharmacy' ? 'pharmacy' : role;
  const heading: Record<Workspace, string> = {
    patient: t('Il mio percorso di cura', 'My care journey'),
    professional: t('La mia attività clinica', 'My clinical work'),
    organization_admin: t('La mia organizzazione', 'My organization'),
    pharmacy: t('La mia farmacia', 'My pharmacy'),
    researcher: t('Spazio ricerca', 'Research workspace'),
    platform: t('Verifiche della piattaforma', 'Platform reviews'),
  };
  const organizationsLink = {id:'workspace-organizations', icon:Building2, title:t('Organizzazioni', 'Organizations')};
  const patientLink = {id:'workspace-patients', icon:FolderHeart, title:t('Anagrafiche e documenti', 'Records and documents')};
  const sharingLink = {id:'workspace-shares', icon:ShieldCheck, title:t('Condivisioni e consensi', 'Sharing and consent')};
  const links = {
    patient: [{id:'workspace-bookings', icon:CalendarDays, title:t('Prenotazioni e farmacia', 'Appointments and pharmacies')}, patientLink, sharingLink],
    professional: [patientLink, sharingLink, organizationsLink],
    organization_admin: [organizationsLink, ...(selectedKind ? [{id:'workspace-management', icon:ClipboardList, title:t('Gestisci struttura', 'Manage organization')}] : []), patientLink],
    pharmacy: [{id:'workspace-management', icon:ClipboardList, title:t('Catalogo e richieste', 'Catalog and requests')}, organizationsLink],
    researcher: [organizationsLink, ...(selectedKind === 'research' ? [{id:'workspace-research', icon:FlaskConical, title:t('Archivio di ricerca', 'Research archive')}] : [])],
    platform: [{id:'workspace-reviews', icon:ShieldCheck, title:t('Verifiche professionali', 'Professional reviews')},
      {id:'workspace-review-research', icon:FlaskConical, title:t('Approvazioni ricerca', 'Research approvals')}, organizationsLink],
  }[workspace];
  const unread = {id:'workspace-notifications', icon:Bell, title:t('Notifiche non lette', 'Unread notifications')};
  const shortcuts = notifications ? [...links, unread] : links;
  const metrics = [
    {value:patients, label:t('Anagrafiche caricate', 'Records loaded'), icon:UsersRound},
    {value:organizations, label:t('Organizzazioni caricate', 'Organizations loaded'), icon:Building2},
    {value:notifications, label:t('Notifiche non lette', 'Unread notifications'), icon:Bell},
  ];
  return <section className="identity-card workspace-overview" aria-labelledby="workspace-heading">
    <div className="workspace-heading">
      <p className="workspace-kicker">{t('Area personale', 'Your workspace')}</p>
      <h2 id="workspace-heading">{heading[workspace]}</h2>
    </div>
    <dl className="workspace-metrics">
      {metrics.map(({value, label, icon: Icon}) => <div key={label}>
        <Icon size={18} aria-hidden="true"/><dt>{label}</dt><dd>{value}</dd>
      </div>)}
    </dl>
    <nav aria-label={t('Accesso rapido', 'Quick navigation')} className="workspace-shortcuts">
      {shortcuts.map(({id, title, icon: Icon}) => <a href={'#' + id} key={id}>
        <Icon size={18} aria-hidden="true"/><span>{title}</span><ArrowUpRight size={16} aria-hidden="true"/>
      </a>)}
    </nav>
  </section>;
}
