export const AUTH_COOKIE = "fa_auth";
export const AUTH_MAX_AGE = 60 * 60 * 24 * 365; // 1 year

function getPassword(): string {
  return process.env.APP_PASSWORD ?? "1718";
}

export async function tokenFor(password: string): Promise<string> {
  const data = new TextEncoder().encode(`fin-assist:${password}`);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function expectedToken(): Promise<string> {
  return tokenFor(getPassword());
}

export async function checkPassword(input: string): Promise<boolean> {
  return input === getPassword();
}
