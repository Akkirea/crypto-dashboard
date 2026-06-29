export function fmtPrice(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, {
    minimumFractionDigits: value > 1000 ? 2 : 4,
    maximumFractionDigits: value > 1000 ? 2 : 6
  });
}

export function fmtQty(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: 5 });
}

export function fmtTime(ms?: number | null) {
  if (!ms) return "—";
  return new Date(ms).toLocaleTimeString();
}

export function fmtBytes(bytes?: number | null) {
  if (bytes === undefined || bytes === null || Number.isNaN(bytes)) return "—";
  if (bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const index = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / 1024 ** index;
  return `${value.toLocaleString(undefined, {
    maximumFractionDigits: value >= 10 ? 1 : 2
  })} ${units[index]}`;
}

export function fmtCompact(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return value.toLocaleString(undefined, { notation: "compact", maximumFractionDigits: 1 });
}

export function fmtUsdCompact(value?: number | null) {
  if (value === undefined || value === null || Number.isNaN(value)) return "—";
  return `$${value.toLocaleString(undefined, { notation: "compact", maximumFractionDigits: 2 })}`;
}

export function toNumber(value?: number | string | null) {
  if (value === undefined || value === null) return null;
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}
