import type { Metadata } from 'next';
import { PortalTheme } from './PortalTheme';
import './globals.css';
import './identity.css';

export const metadata: Metadata = {
  title: 'Health Collaboration',
  description: 'Spazio digitale per pazienti, professionisti e organizzazioni sanitarie.',
  icons: { icon: '/favicon.svg' },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return <html lang="it" suppressHydrationWarning><body><PortalTheme>{children}</PortalTheme></body></html>;
}
