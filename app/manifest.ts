import type {MetadataRoute} from 'next';

export default function manifest(): MetadataRoute.Manifest {
  return {
    id: '/',
    name: 'Clarìa',
    short_name: 'Clarìa',
    description: 'Spazio di cura per pazienti, professionisti e organizzazioni.',
    start_url: '/',
    scope: '/',
    display: 'standalone',
    lang: 'it',
    background_color: '#faf8fd',
    theme_color: '#6d28d9',
    icons: [
      {src: '/claria-192.png', sizes: '192x192', type: 'image/png', purpose: 'any'},
      {src: '/claria-512.png', sizes: '512x512', type: 'image/png', purpose: 'any'},
    ],
  };
}
