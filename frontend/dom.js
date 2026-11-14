// Small DOM and HTTP helpers shared by the Admin pages (Forecast, Optimize,
// Experiments). The member site keeps its own helpers on purpose.

export const $ = (id) => document.getElementById(id);

/** Create an element with optional text content and class name. */
export function element(tag, text, className) {
  const el = document.createElement(tag);
  if (text !== undefined) el.textContent = text;
  if (className) el.className = className;
  return el;
}

/** Run ids and similar keys must match the server's identifier rule. */
export const safeId = (value) => typeof value === 'string' && /^[A-Za-z0-9_-]{1,80}$/.test(value);

/**
 * GET (no body) or POST (JSON body) and return the parsed JSON response.
 * Throws an Error whose message is suitable for showing to the user.
 */
export async function requestJson(path, body, { signal, unreadable, failed } = {}) {
  const init =
    body === undefined
      ? { method: 'GET', signal }
      : { method: 'POST', signal, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
  const response = await fetch(path, init);
  let data;
  try {
    data = await response.json();
  } catch {
    throw new Error(unreadable || `The server returned an unreadable response (${response.status}).`);
  }
  if (!response.ok) {
    const message = typeof data.error === 'string' ? data.error : data.message;
    throw new Error(message || failed || `Request failed (${response.status}).`);
  }
  return data;
}
