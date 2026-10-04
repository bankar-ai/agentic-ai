/** Decode a JWT's payload without verifying its signature -- only ever used to read the `exp`
 * claim for a client-side expiry warning (AGT-026). Never trust this for anything that matters;
 * the backend is the real authority on whether a token is still valid.
 */
export function decodeJwtExpiry(token: string): number | null {
  try {
    const payload = token.split(".")[1];
    if (!payload) return null;
    const decoded = JSON.parse(atob(payload.replace(/-/g, "+").replace(/_/g, "/")));
    return typeof decoded.exp === "number" ? decoded.exp * 1000 : null;
  } catch {
    return null;
  }
}
