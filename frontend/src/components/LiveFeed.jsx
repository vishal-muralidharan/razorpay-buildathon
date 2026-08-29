import { CATEGORY_LABEL, CATEGORY_COLOR, formatDateTime } from "../utils";

const OUTCOME_STYLE = {
  PENDING: "text-paper-100/50",
  SUCCESS: "text-moss-500",
  FAILURE: "text-clay-500",
};

export default function LiveFeed({ feed, onSelect }) {
  return (
    <div className="border border-paper-100/10 rounded-lg bg-ink-800/60 p-5 h-full flex flex-col">
      <div className="text-[11px] uppercase tracking-[0.14em] text-paper-100/50 font-body mb-3">
        Live decision feed
      </div>
      <div className="flex-1 overflow-y-auto scrollbar-thin space-y-1 pr-1 max-h-[420px]">
        {feed.length === 0 && (
          <div className="text-sm text-paper-100/40 font-body py-6 text-center">
            No retry decisions yet — diagnose and schedule a transaction to see it here.
          </div>
        )}
        {feed.map((item, i) => (
          <button
            key={`${item.transaction_id}-${item.decided_at}-${i}`}
            onClick={() => onSelect(item.transaction_id)}
            className="w-full text-left px-3 py-2.5 rounded-md hover:bg-paper-100/5 transition-colors border-b border-paper-100/5 last:border-0"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2 min-w-0">
                <span
                  className="w-1.5 h-1.5 rounded-full shrink-0"
                  style={{ background: CATEGORY_COLOR[item.decline_category] }}
                />
                <span className="font-body text-sm text-paper-50 truncate">
                  {item.customer_name}
                </span>
                <span className="font-mono text-[11px] text-paper-100/40 shrink-0">
                  #{item.transaction_id}
                </span>
              </div>
              <span className={`font-mono text-[11px] shrink-0 ${OUTCOME_STYLE[item.outcome]}`}>
                {item.outcome}
              </span>
            </div>
            <div className="flex items-center justify-between mt-0.5 pl-3.5">
              <span className="font-body text-xs text-paper-100/50">
                {CATEGORY_LABEL[item.decline_category]} → {formatDateTime(item.predicted_window)}
              </span>
              <span className="font-mono text-[11px] text-paper-100/40">
                {Math.round(item.predicted_success_prob * 100)}% conf.
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
