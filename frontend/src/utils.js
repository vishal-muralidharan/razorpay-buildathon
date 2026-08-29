export const CATEGORY_LABEL = {
  INSUFFICIENT_FUNDS: "Insufficient funds",
  BANK_OUTAGE: "Bank outage",
  MANDATE_EXPIRED: "Mandate expired",
  MANDATE_CANCELLED: "Mandate cancelled",
  UNKNOWN: "Unclassified",
};

export const CATEGORY_COLOR = {
  INSUFFICIENT_FUNDS: "#D9A441", // amber
  BANK_OUTAGE: "#5B8FD9",        // steel blue
  MANDATE_EXPIRED: "#B23B3B",    // clay
  MANDATE_CANCELLED: "#8A6BAE",  // muted violet
  UNKNOWN: "#7A8AA0",
};

export const STATUS_LABEL = {
  PENDING: "Pending diagnosis",
  SCHEDULED: "Retry scheduled",
  AWAITING_CUSTOMER: "Awaiting customer",
  RECOVERED: "Recovered",
  EXHAUSTED: "Cap exhausted",
  CANCELLED: "Mandate dead",
};

export const STATUS_STYLE = {
  PENDING: "bg-ink-700 text-paper-100 border-ink-700/60",
  SCHEDULED: "bg-amber-500/15 text-amber-400 border-amber-500/40",
  AWAITING_CUSTOMER: "bg-[#5B8FD9]/15 text-[#8FB4EA] border-[#5B8FD9]/40",
  RECOVERED: "bg-moss-500/15 text-moss-500 border-moss-500/40",
  EXHAUSTED: "bg-clay-500/15 text-clay-500 border-clay-500/40",
  CANCELLED: "bg-[#8A6BAE]/15 text-[#B79CD6] border-[#8A6BAE]/40",
};

export function formatINR(amount) {
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(amount || 0);
}

export function formatDateTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function shortHash(hash) {
  if (!hash) return "";
  return `${hash.slice(0, 8)}…${hash.slice(-6)}`;
}
