export const CATEGORY_LABEL = {
  INSUFFICIENT_FUNDS: "Insufficient funds",
  BANK_OUTAGE: "Bank outage",
  MANDATE_EXPIRED: "Mandate expired",
  MANDATE_CANCELLED: "Mandate cancelled",
  UNKNOWN: "Unclassified",
};

export const CATEGORY_COLOR = {
  INSUFFICIENT_FUNDS: "#F59E0B", // warning amber
  BANK_OUTAGE: "#0D94FB",        // rzp blue
  MANDATE_EXPIRED: "#EF4444",    // error red
  MANDATE_CANCELLED: "#4B5563",  // dark gray
  UNKNOWN: "#9CA3AF",
};

export const STATUS_LABEL = {
  PENDING: "Pending diagnosis",
  SCHEDULED: "Retry scheduled",
  PENDING_CONFIRMATION: "Awaiting bank confirmation",
  AWAITING_CUSTOMER: "Awaiting customer",
  RECOVERED: "Recovered",
  EXHAUSTED: "Retries used up",
  CANCELLED: "Mandate cancelled",
};

export const STATUS_STYLE = {
  PENDING: "bg-gray-100 text-gray-600 border-gray-200",
  SCHEDULED: "bg-status-warning_bg text-status-warning border-status-warning/40",
  PENDING_CONFIRMATION: "bg-rzp-lightblue text-rzp-blue border-rzp-blue/40",
  AWAITING_CUSTOMER: "bg-rzp-lightblue text-rzp-blue border-rzp-blue/40",
  RECOVERED: "bg-status-success_bg text-status-success border-status-success/40",
  EXHAUSTED: "bg-status-error_bg text-status-error border-status-error/40",
  CANCELLED: "bg-gray-200 text-gray-700 border-gray-300",
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
  // SQLite/FastAPI drops the timezone, but we know it's UTC.
  // Append 'Z' to force JavaScript to parse it as UTC instead of local time.
  const dateStr = iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z";
  const d = new Date(dateStr);
  return d.toLocaleString("en-IN", {
    timeZone: "Asia/Kolkata",
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
