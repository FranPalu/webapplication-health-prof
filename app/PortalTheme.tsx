'use client';

import { ThemeProvider, useTheme } from 'next-themes';
import { useEffect, type ReactNode } from 'react';

export function PortalTheme({ children }: { children: ReactNode }) {
  return <ThemeProvider attribute="data-theme" storageKey="health-theme" defaultTheme="light" enableSystem={false}>{children}</ThemeProvider>;
}

export function ThemePicker({ english = false }: { english?: boolean }) {
  const { theme, setTheme } = useTheme();
  useEffect(() => {
    if (theme === 'system') setTheme('light');
  }, [theme, setTheme]);
  return (
    <label>
      {english ? 'Appearance' : 'Aspetto'}
      <select value={theme === 'dark' ? 'dark' : 'light'} onChange={event => setTheme(event.target.value)} suppressHydrationWarning>
        <option value="light">Light mode</option>
        <option value="dark">Dark mode</option>
      </select>
    </label>
  );
}
