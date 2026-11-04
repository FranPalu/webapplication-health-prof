'use client';

import { ThemeProvider, useTheme } from 'next-themes';
import type { ReactNode } from 'react';

export function PortalTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider attribute="data-theme" storageKey="health-theme">{children}</ThemeProvider>;
}

export function ThemePicker({ english = false }: { english?: boolean }) {
  const { theme, setTheme } = useTheme();
  return (
    <label>
      {english ? 'Appearance' : 'Aspetto'}
      <select value={theme ?? 'system'} onChange={event => setTheme(event.target.value)} suppressHydrationWarning>
        <option value="system">{english ? 'System' : 'Sistema'}</option>
        <option value="light">{english ? 'Light' : 'Chiaro'}</option>
        <option value="dark">{english ? 'Dark' : 'Scuro'}</option>
      </select>
    </label>
  );
}
