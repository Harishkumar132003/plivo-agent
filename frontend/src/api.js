// Empty string → relative URLs, so requests go to whatever origin served the page.
// Set VITE_BACKEND_URL only when the frontend is hosted separately from the API.
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "";

export function getApiUrl(path) {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${BACKEND_URL}${cleanPath}`;
}
