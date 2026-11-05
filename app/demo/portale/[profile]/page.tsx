import {notFound} from 'next/navigation';
import {DemoWorkspace} from '../../DemoWorkspace';
import {profiles, type Profile} from '../../profiles';

export function generateStaticParams() {
  return Object.keys(profiles).map(profile => ({profile}));
}

export async function generateMetadata({params}: {params: Promise<{profile: string}>}) {
  const {profile} = await params;
  if (!Object.hasOwn(profiles, profile)) return {};
  return {title: `Clarìa · ${profiles[profile as Profile].label}`};
}

export default async function DemoWorkspacePage({params}: {params: Promise<{profile: string}>}) {
  const {profile} = await params;
  if (!Object.hasOwn(profiles, profile)) notFound();
  return <DemoWorkspace key={profile} role={profile as Profile}/>;
}
