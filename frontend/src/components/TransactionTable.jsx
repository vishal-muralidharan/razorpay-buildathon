import { CATEGORY_LABEL, STATUS_LABEL, STATUS_STYLE, formatINR, formatDateTime } from "../utils";

export default function TransactionTable({
  transactions, filters, onFilterChange, onSelect, loading,
}) {
  return (
    <div className="border border-paper-100/10 rounded-lg bg-ink-800/60 overflow-hidden">
      <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4 border-b border-paper-100/10">
        <div className="text-[11px] uppercase tracking-[0.14em] text-paper-100/50 font-body">
          Failed transactions
        </div>
        <div className="flex gap-2">
          <select
            value={filters.category}
            onChange={(e) => onFilterChange({ ...filters, category: e.target.value })}
            className="bg-ink-900 border border-paper-100/15 text-paper-100/80 text-xs font-mono rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-amber-400"
          >
            <option value="">All categories</option>
            {Object.entries(CATEGORY_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
          <select
            value={filters.status}
            onChange={(e) => onFilterChange({ ...filters, status: e.target.value })}
            className="bg-ink-900 border border-paper-100/15 text-paper-100/80 text-xs font-mono rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-amber-400"
          >
            <option value="">All statuses</option>
            {Object.entries(STATUS_LABEL).map(([k, v]) => (
              <option key={k} value={k}>{v}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="overflow-x-auto scrollbar-thin max-h-[420px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-ink-800 z-10">
            <tr className="text-left text-[11px] uppercase tracking-wide text-paper-100/40 font-body">
              <th className="px-5 py-2.5 font-medium">Customer</th>
              <th className="px-5 py-2.5 font-medium">Amount</th>
              <th className="px-5 py-2.5 font-medium">Decline code</th>
              <th className="px-5 py-2.5 font-medium">Category</th>
              <th className="px-5 py-2.5 font-medium">Status</th>
              <th className="px-5 py-2.5 font-medium">Attempts</th>
              <th className="px-5 py-2.5 font-medium">Failed at</th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr><td colSpan={7} className="px-5 py-8 text-center text-paper-100/40 font-body">Loading…</td></tr>
            )}
            {!loading && transactions.length === 0 && (
              <tr><td colSpan={7} className="px-5 py-8 text-center text-paper-100/40 font-body">No transactions match these filters.</td></tr>
            )}
            {transactions.map((t) => (
              <tr
                key={t.id}
                onClick={() => onSelect(t.id)}
                className="border-t border-paper-100/5 hover:bg-paper-100/5 cursor-pointer transition-colors"
              >
                <td className="px-5 py-2.5 font-body text-paper-50">{t.customer_name}</td>
                <td className="px-5 py-2.5 font-mono text-paper-100/80">{formatINR(t.amount)}</td>
                <td className="px-5 py-2.5 font-mono text-paper-100/60">{t.decline_code}</td>
                <td className="px-5 py-2.5 font-body text-paper-100/70">{CATEGORY_LABEL[t.decline_category]}</td>
                <td className="px-5 py-2.5">
                  <span className={`inline-block px-2 py-0.5 rounded border text-[11px] font-mono ${STATUS_STYLE[t.status]}`}>
                    {STATUS_LABEL[t.status]}
                  </span>
                </td>
                <td className="px-5 py-2.5 font-mono text-paper-100/60">{t.retry_count}/3</td>
                <td className="px-5 py-2.5 font-mono text-paper-100/50 text-xs">{formatDateTime(t.failed_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
