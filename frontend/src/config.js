// API Configuration
// In production (Vercel), this will be the same origin (same domain)
// In development (localhost), this can be overridden with VITE_API_URL

export const API_BASE_URL = import.meta.env.VITE_API_URL ||
  (import.meta.env.DEV ? '' : (typeof window !== 'undefined' ? window.location.origin : ''));

export const API_ENDPOINTS = {
  login: `${API_BASE_URL}/api/login`,
  changes: `${API_BASE_URL}/api/changes`,
  portals: `${API_BASE_URL}/api/portals`,
  diffs: `${API_BASE_URL}/api/diffs`,
  crawlLog: `${API_BASE_URL}/api/crawl-log`,
  crawlStatus: `${API_BASE_URL}/api/crawl/status`,
  crawlStart: `${API_BASE_URL}/api/crawl/start`,
  crawlStop: `${API_BASE_URL}/api/crawl/stop`,
};
