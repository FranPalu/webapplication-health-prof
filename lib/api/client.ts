import type { paths } from './schema';
export type ApiPath = keyof paths;
export async function api<T>(path: string, body?: unknown): Promise<T> {
  const csrf = document.cookie.split('; ').find(x => x.startsWith('csrftoken='))?.split('=')[1] || '';
  const response = await fetch(`/api/v1/${path}`, {
    method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': decodeURIComponent(csrf)},
    ...(body === undefined ? {} : {body: JSON.stringify(body)}),
  });
  const value: unknown = await response.json();
  if (!response.ok) throw new Error(JSON.stringify(value));
  return value as T;
}
