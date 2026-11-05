import type { paths } from './schema';
export type ApiPath = keyof paths;

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
  }
}
export async function api<T>(path: string, body?: unknown, method?: 'DELETE'): Promise<T> {
  const csrf = document.cookie.split('; ').find(x => x.startsWith('csrftoken='))?.split('=')[1] || '';
  const multipart = body instanceof FormData;
  const response = await fetch(`/api/v1/${path}`, {
    method: method ?? (body === undefined ? 'GET' : 'POST'), credentials: 'same-origin',
    headers: {...(multipart ? {} : {'Content-Type': 'application/json'}), 'X-CSRFToken': decodeURIComponent(csrf)},
    ...(body === undefined ? {} : {body: multipart ? body : JSON.stringify(body)}),
  });
  if (response.status === 204) return undefined as T;
  const value: unknown = await response.json().catch(() => undefined);
  if (!response.ok) throw new ApiError(response.status, JSON.stringify(value) ?? '');
  if (value === undefined) throw new ApiError(502, 'Unexpected API response.');
  return value as T;
}
