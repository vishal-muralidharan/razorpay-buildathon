import { formatINR } from "../utils";

function Stat({ label, value, accent, sub }) {
  return (
    <div className="flex-1 min-w-[160px] border border-paper-100/10 rounded-lg px-5 py-4 bg-ink-800/60">
      <div className="text-[11px] uppercase tracking-[0.14em] text-paper-100/50 font-body">
        {label}
      </div>
      <div className={`font-display text-2xl md:text-3xl mt-1 ${accent}`}>{value}</div>
      {sub && <div className="text-xs text-paper-100/40 mt-1 font-mono">{sub}</div>}
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
        accent="text-moss-500"
        sub={`${summary.recovered_count} transactions`}
      />
      <Stat
        label="Still at risk"
        value={formatINR(summary.total_at_risk)}
        accent="text-amber-400"
        sub={`${summary.pending_count} in flight`}
      />
      <Stat
        label="Recovery rate"
        value={`${summary.recovery_rate_pct}%`}
        accent="text-paper-50"
        sub={`of ${summary.total_transactions} failures`}
      />
      <Stat
        label="Cap exhausted"
        value={summary.exhausted_count}
        accent="text-clay-500"
        sub="3/3 NPCI attempts used"
      />
      <Stat
        label="Wasted retries avoided"
        value={summary.api_calls_saved_estimate}
        accent="text-[#8FB4EA]"
        sub="vs. blind 24h retries"
      />
    </div>
  );
}
