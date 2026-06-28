const RAILWAY_HTTP_URL = "https://backend-production-bd2c.up.railway.app";
const RAILWAY_WS_URL = "wss://backend-production-bd2c.up.railway.app/ws/market";

function isLocalBrowser(): boolean {
  if (typeof window === "undefined") return true;
  return ["localhost", "127.0.0.1"].includes(window.location.hostname);
}

export function backendHttpUrl(): string {
  return (
    process.env.NEXT_PUBLIC_BACKEND_HTTP_URL ??
    (isLocalBrowser() ? "http://localhost:8000" : RAILWAY_HTTP_URL)
  );
}

export function backendWsUrl(): string {
  return (
    process.env.NEXT_PUBLIC_BACKEND_WS_URL ??
    (isLocalBrowser() ? "ws://localhost:8000/ws/market" : RAILWAY_WS_URL)
  );
}
