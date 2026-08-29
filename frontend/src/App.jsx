import { useEffect, useState, useCallback } from "react";
import { api } from "./api";
import KpiStrip from "./components/KpiStrip";
import CategoryChart from "./components/CategoryChart";
import LiveFeed from "./components/LiveFeed";
import TransactionTable from "./components/TransactionTable";
import AuditDrawer from "./components/AuditDrawer";

const POLL_MS = 8000;

export default function App() {
  const [summary, setSummary] = useState(null);
  const [feed, setFeed] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [filters, setFilters] = useState({ category: "", status: "" });
  const [selectedTxn, setSelectedTxn] = useState(null);
  const [loadingTxns, setLoadingTxns] = useState(true);
  const [connError, setConnError] = useState(false);

  const refresh = useCallback(async () => {
    try {
      const [s, f] = await Promise.all([api.getSummary(), api.getLiveFeed(15)]);
      setSummary(s);
      setFeed(f);
      setConnError(false);
    } catch {
      setConnError(true);
    }
  }, []);

  const refreshTransactions = useCallback(async () => {
    setLoadingTxns(true);
    try {
      const params = {};
      if (filters.category) params.category = filters.category;
      if (filters.status) params.status = filters.status;
      const t = await api.listTransactions(params);
      setTransactions(t);
    } catch {
      /* surfaced via connError from refresh() */
    } finally {
      setLoadingTxns(false);
    }
  }, [filters]);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, POLL_MS);
    return () => clearInterval(id);
  }, [refresh]);

  useEffect(() => {
    refreshTransactions();
  }, [refreshTransactions]);

  function handleChanged() {
    refresh();
    refreshTransactions();
  }

  return (
    <div className="min-h-screen font-body text-rzp-navy">
      <header className="border-b border-rzp-border px-6 md:px-10 py-6 bg-white shadow-sm">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-[0.2em] text-rzp-blue font-mono mb-1 font-semibold">
              Track 03 · AI Revenue Recovery
            </div>
            <h1 className="font-display text-2xl md:text-3xl text-rzp-navy font-bold">
              Mandate Resurrection Agent
            </h1>
            <p className="text-sm text-gray-500 mt-1 max-w-xl font-body">
              Diagnoses failed UPI Autopay / e-NACH debits, predicts the retry window most
              likely to succeed, and spends NPCI's 3-attempt budget on purpose instead of by habit.
            </p>
          </div>
          {connError && (
            <div className="text-xs font-mono text-status-error border border-status-error/40 rounded px-3 py-1.5 bg-status-error/10">
              Backend unreachable — is uvicorn running on :8000?
            </div>
          )}
        </div>
      </header>

      <main className="max-w-7xl mx-auto px-6 md:px-10 py-8 space-y-6">
        <KpiStrip summary={summary} />

        <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
          <div className="lg:col-span-3">
            <CategoryChart summary={summary} />
          </div>
          <div className="lg:col-span-2">
            <LiveFeed feed={feed} onSelect={setSelectedTxn} />
          </div>
        </div>

        <TransactionTable
          transactions={transactions}
          filters={filters}
          onFilterChange={setFilters}
          onSelect={setSelectedTxn}
          loading={loadingTxns}
        />
      </main>

      <footer className="max-w-7xl mx-auto px-6 md:px-10 pb-10 text-xs text-gray-400 font-mono">
        Compliance rules enforced server-side: max 3 NPCI retries/cycle · no scheduling 18:00–21:00 ·
        every decision hash-chained in the audit ledger.
      </footer>

      <AuditDrawer
        transactionId={selectedTxn}
        onClose={() => setSelectedTxn(null)}
        onChanged={handleChanged}
      />
    </div>
  );
}
