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
