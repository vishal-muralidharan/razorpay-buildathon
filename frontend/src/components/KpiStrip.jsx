import { formatINR } from "../utils";

function Stat({ label, value, accent, sub }) {
  return (
    <div className="flex-1 min-w-[160px] border border-rzp-border rounded-lg px-5 py-4 bg-white shadow-sm">
      <div className="text-[11px] uppercase tracking-[0.14em] text-gray-500 font-body">
        {label}
      </div>
      <div className={`font-display text-2xl md:text-3xl mt-1 font-bold ${accent}`}>{value}</div>
      {sub && <div className="text-xs text-gray-400 mt-1 font-mono">{sub}</div>}
    </div>
  );
}

export default function KpiStrip({ summary }) {
  if (!summary) return null;

  return (
    <div className="flex flex-wrap gap-3">
      <Stat
        label="Recovered"
        value={formatINR(summary.total_recovered)}
        accent="text-status-success"
        sub={`${summary.recovered_count} transactions`}
      />
      <Stat
        label="Still at risk"
        value={formatINR(summary.total_at_risk)}
        accent="text-status-warning"
        sub={`${summary.pending_count} in flight`}
      />
      <Stat
        label="Recovery rate"
        value={`${summary.recovery_rate_pct}%`}
        accent="text-rzp-navy"
        sub={`of ${summary.total_transactions} failures`}
      />
      <Stat
        label="Cap exhausted"
        value={summary.exhausted_count}
        accent="text-status-error"
        sub="3/3 NPCI attempts used"
      />
      <Stat
        label="Wasted retries avoided"
        value={summary.api_calls_saved_estimate}
        accent="text-rzp-blue"
        sub="vs. blind 24h retries"
      />
    </div>
  );
}
