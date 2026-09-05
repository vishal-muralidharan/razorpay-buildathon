import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "./api";

export default function Schedule() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");

  const [txnId, setTxnId] = useState(null);
  const [date, setDate] = useState("");
  const [status, setStatus] = useState("idle"); // idle, loading, success, error
  const [errorMsg, setErrorMsg] = useState("");

  useEffect(() => {
    if (token) {
      try {
        const payload = JSON.parse(atob(token.split(".")[1]));
        if (payload.txn_id) {
          setTxnId(payload.txn_id);
        } else {
          setStatus("error");
          setErrorMsg("Invalid link: Missing transaction reference.");
        }
      } catch (e) {
        setStatus("error");
        setErrorMsg("Invalid link: The URL appears to be malformed.");
      }
    } else {
      setStatus("error");
      setErrorMsg("Missing token: Please use the link provided in your message.");
    }
  }, [token]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!date) return;
    setStatus("loading");
    setErrorMsg("");

    try {
      // Convert local date selection to a full ISO string
      const chosenDate = new Date(date).toISOString();
      await api.chooseDate(txnId, chosenDate, token);
      setStatus("success");
    } catch (err) {
      setStatus("error");
      setErrorMsg(err.message || "Failed to schedule retry. Your link may have expired.");
    }
  };

  if (status === "error" && !txnId) {
    return (
      <div className="max-w-xl mx-auto mt-20 p-8 bg-white rounded shadow-sm border border-rzp-border">
        <h2 className="text-xl font-bold text-status-error mb-2">Link Invalid</h2>
        <p className="text-gray-600">{errorMsg}</p>
      </div>
    );
  }

  return (
    <div className="max-w-xl mx-auto mt-20 p-8 bg-white rounded shadow-sm border border-rzp-border">
      {status === "success" ? (
        <div className="text-center py-6">
          <div className="w-16 h-16 bg-green-100 text-status-success rounded-full flex items-center justify-center mx-auto mb-4">
            <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h2 className="text-2xl font-bold text-rzp-navy mb-2">Payment Scheduled</h2>
          <p className="text-gray-600 mb-6">
            We've paused automatic retries and will attempt your payment on the date you picked.
          </p>
        </div>
      ) : (
        <>
          <h2 className="text-2xl font-bold text-rzp-navy mb-2">Schedule your payment</h2>
          <p className="text-gray-500 mb-6 text-sm">
            Choose a date before the end of your billing cycle to retry your pending UPI Autopay mandate.
          </p>

          <form onSubmit={handleSubmit} className="space-y-6">
            <div>
              <label htmlFor="date" className="block text-sm font-medium text-rzp-navy mb-2">
                Preferred Retry Date
              </label>
              <input
                type="date"
                id="date"
                required
                min={new Date().toISOString().split("T")[0]}
                value={date}
                onChange={(e) => setDate(e.target.value)}
                className="w-full border border-gray-300 rounded px-4 py-2 focus:outline-none focus:ring-1 focus:ring-rzp-blue focus:border-rzp-blue"
              />
            </div>

            {status === "error" && errorMsg && (
              <div className="p-3 bg-red-50 text-status-error text-sm rounded border border-red-100">
                {errorMsg}
              </div>
            )}

            <button
              type="submit"
              disabled={status === "loading" || !date}
              className="w-full bg-rzp-blue hover:bg-blue-600 text-white font-medium py-3 px-4 rounded transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {status === "loading" ? "Scheduling..." : "Confirm Date"}
            </button>
          </form>
        </>
      )}
    </div>
  );
}
