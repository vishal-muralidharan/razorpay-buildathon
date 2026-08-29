const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      /* ignore parse errors */
    }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res.json();
}

export const api = {
  getSummary: () => request("/dashboard/summary"),
  getLiveFeed: (limit = 20) => request(`/dashboard/live-feed?limit=${limit}`),
  listTransactions: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return request(`/transactions${qs ? `?${qs}` : ""}`);
  },
  getTransaction: (id) => request(`/transactions/${id}`),
  diagnose: (transaction_id) =>
    request("/diagnose", { method: "POST", body: JSON.stringify({ transaction_id }) }),
  predictWindow: (customerId) => request(`/predict-retry-window/${customerId}`),
  scheduleRetry: (transaction_id) =>
    request("/schedule-retry", { method: "POST", body: JSON.stringify({ transaction_id }) }),
  executeRetry: (transaction_id) =>
    request("/execute-retry", { method: "POST", body: JSON.stringify({ transaction_id }) }),
  chooseDate: (transaction_id, chosen_date) =>
    request("/customer-choose-date", {
      method: "POST",
      body: JSON.stringify({ transaction_id, chosen_date }),
    }),
  getAudit: (transactionId) => request(`/audit/${transactionId}`),
};
