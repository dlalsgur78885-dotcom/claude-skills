import { config } from './config.js';

/** 캐러셀 백엔드 클라이언트.
 *
 *  대시보드가 쓰는 것과 **똑같은 HTTP API** 를 탄다. 백엔드 코드를 직접 임포트하지
 *  않는 이유: 인증 우회 경로를 만들지 않기 위해서다. 봇은 그냥 계정 하나로 로그인한
 *  또 한 명의 사용자이고, 권한 규칙이 저절로 같아진다.
 *
 *  토큰은 계정별로 캐시한다(14일 만료지만 401 이면 한 번 다시 로그인한다).
 */
const tokens = new Map(); // username → access_token

async function login({ username, password }) {
  const res = await fetch(`${config.apiBase}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(`로그인 실패(${username}): ${res.status} ${detail.slice(0, 120)}`);
  }
  const data = await res.json();
  if (!data?.access_token) throw new Error(`로그인 응답에 토큰이 없습니다(${username}).`);
  tokens.set(username, data.access_token);
  return data.access_token;
}

async function tokenFor(account) {
  return tokens.get(account.username) || login(account);
}

/** 계정 권한으로 API 호출. 401 이면 토큰을 버리고 한 번만 재시도한다. */
export async function apiFetch(account, method, path, { query, body } = {}) {
  const url = new URL(`${config.apiBase}${path}`);
  for (const [k, v] of Object.entries(query || {})) {
    if (v !== undefined && v !== null && v !== '') url.searchParams.set(k, String(v));
  }

  const send = async (token) =>
    fetch(url, {
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        ...(body ? { 'Content-Type': 'application/json' } : {})
      },
      body: body ? JSON.stringify(body) : undefined
    });

  let res = await send(await tokenFor(account));
  if (res.status === 401) {
    tokens.delete(account.username);
    res = await send(await login(account));
  }

  if (!res.ok) {
    let detail = '';
    try {
      const parsed = await res.json();
      detail = parsed?.detail ? String(parsed.detail) : JSON.stringify(parsed).slice(0, 200);
    } catch {
      detail = (await res.text().catch(() => '')).slice(0, 200);
    }
    throw new Error(`${method} ${path} 실패 (${res.status}): ${detail}`);
  }

  if (res.status === 204) return null;
  const text = await res.text();
  return text ? JSON.parse(text) : null;
}

export const api = {
  me: (a) => apiFetch(a, 'GET', '/auth/me'),

  channels: (a) => apiFetch(a, 'GET', '/channels/'),
  deleteChannel: (a, id) => apiFetch(a, 'DELETE', `/channels/${id}`),
  updateChannel: (a, id, body) => apiFetch(a, 'PATCH', `/channels/${id}`, { body }),
  createChannel: (a, body) => apiFetch(a, 'POST', '/channels/', { body }),

  posts: (a, query) => apiFetch(a, 'GET', '/posts/', { query }),
  post: (a, id) => apiFetch(a, 'GET', `/posts/${id}`),

  categories: (a) => apiFetch(a, 'GET', '/categories/'),
  createCategory: (a, body) => apiFetch(a, 'POST', '/categories/', { body }),
  updateCategory: (a, id, body) => apiFetch(a, 'PATCH', `/categories/${id}`, { body }),
  deleteCategory: (a, id) => apiFetch(a, 'DELETE', `/categories/${id}`),

  templates: (a) => apiFetch(a, 'GET', '/templates/'),
  layouts: (a) => apiFetch(a, 'GET', '/templates/layouts'),

  carousels: (a, query) => apiFetch(a, 'GET', '/carousels/', { query }),
  deleteCarousel: (a, id) => apiFetch(a, 'DELETE', `/carousels/${id}`),

  scrapeStatus: (a) => apiFetch(a, 'GET', '/scrape/status'),
  scrapeAll: (a) => apiFetch(a, 'POST', '/scrape/run'),
  scrapeChannel: (a, handle) =>
    apiFetch(a, 'POST', `/scrape/channel/${encodeURIComponent(handle)}`)
};
