export function fmt(n: number) {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `$${(abs / 1_000_000).toFixed(1)}M`;
  if (abs >= 1_000) return `$${abs.toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
  return `$${abs.toFixed(2)}`;
}

export function monthLabel(p: string) {
  const [y, m] = p.split("-");
  return new Date(+y, +m - 1).toLocaleDateString("en-US", { month: "long", year: "numeric" });
}

export function shortMonth(p: string) {
  const [y, m] = p.split("-");
  return new Date(+y, +m - 1).toLocaleDateString("en-US", { month: "short" });
}
