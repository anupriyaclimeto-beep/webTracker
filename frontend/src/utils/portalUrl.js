export function portalUrl() {
  return import.meta.env.VITE_PORTAL_URL || 'http://localhost:3100';
}

export function redirectToPortalSignedOut() {
  window.location.href = `${portalUrl().replace(/\/$/, '')}/?signedOut=1`;
}
