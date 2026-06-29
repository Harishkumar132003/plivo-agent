const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:7860";

/**
 * Returns the absolute URL for a given API path.
 * @param {string} path - The relative path of the API endpoint (e.g., "/api/login")
 * @returns {string} - The absolute URL (e.g., "http://localhost:7860/api/login")
 */
export function getApiUrl(path) {
  const cleanPath = path.startsWith("/") ? path : `/${path}`;
  return `${BACKEND_URL}${cleanPath}`;
}
