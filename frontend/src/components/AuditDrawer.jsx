import { useEffect, useState } from "react";
import { api } from "../api";
import {
  CATEGORY_LABEL, STATUS_LABEL, STATUS_STYLE, formatINR, formatDateTime, shortHash,
} from "../utils";

const STEP_LABEL = {
  DIAGNOSIS: "Diagnosed",
  RETRY_SCHEDULED: "Retry scheduled",
  SCHEDULING_BLOCKED: "Scheduling blocked",
  SCHEDULING_REJECTED: "Scheduling rejected (compliance cap)",
  SCHEDULING_PAUSED: "Scheduling paused (customer chose date)",
  NUDGE_SENT: "Customer nudge sent",
  RETRY_EXECUTED: "Retry executed",
  RETRY_INITIATED: "Retry sent to bank",
  RETRY_RESCHEDULED_BANK_OUTAGE: "Rescheduled - bank still down",
  WEBHOOK_PAYMENT_CAPTURED: "Bank confirmed payment",
  WEBHOOK_PAYMENT_FAILED: "Bank confirmed failure",
  RECONCILIATION_SWEEP: "Missed retry recovered",
  CUSTOMER_SELF_SCHEDULED: "Customer self-scheduled",
};

function ActionButton({ onClick, children, tone = "default", disabled, busy }) {
  const tones = {
    default: "border-rzp-border text-rzp-navy hover:bg-rzp-gray",
    primary: "border-rzp-blue bg-rzp-blue text-white hover:brightness-110",
    danger: "border-status-error/50 text-status-error hover:bg-status-error/10",
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled || busy}
      className={`px-3 py-1.5 rounded border text-xs font-mono transition-colors disabled:opacity-30 disabled:cursor-not-allowed ${tones[tone]}`}
    >
      {busy ? "…" : children}
    </button>
  );
}

export default function AuditDrawer({ transactionId, onClose, onChanged }) {
  const [detail, setDetail] = useState(null);
  const [auditTrail, setAuditTrail] = useState(null);
  const [error, setError] = useState(null);
  const [busyAction, setBusyAction] = useState(null);

  async function load() {
    try {
      const [d, a] = await Promise.all([
        api.getTransaction(transactionId),
        api.getAudit(transactionId),
      ]);
      setDetail(d);
      setAuditTrail(a);
      setError(null);
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => {
    if (transactionId) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [transactionId]);

  async function runAction(name, fn) {
    setBusyAction(name);
    setError(null);
    try {
      await fn();
      await load();
      onChanged?.();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyAction(null);
    }
  }

  if (!transactionId) return null;

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative w-full max-w-2xl h-full bg-white border-l border-rzp-border shadow-2xl overflow-y-auto scrollbar-thin">
        <div className="sticky top-0 bg-white/95 backdrop-blur border-b border-rzp-border px-6 py-4 flex items-center justify-between z-10">
          <div>
            <div className="text-[11px] uppercase tracking-[0.14em] text-gray-500 font-body">
              Transaction #{transactionId}
            </div>
            <div className="font-display text-lg text-rzp-navy font-bold">
              {detail?.customer?.name || "…"}
            </div>
          </div>
          <button onClick={onClose} className="text-gray-500 hover:text-rzp-navy font-mono text-sm">
            close ✕
          </button>
        </div>

        {error && (
          <div className="mx-6 mt-4 px-4 py-2 rounded border border-status-error/40 bg-status-error/10 text-status-error text-sm font-mono">
            {error}
          </div>
        )}

        {detail && (
          <div className="p-6 space-y-6">
            {/* Summary */}
            <div className="grid grid-cols-2 gap-3 text-sm">
              <div className="border border-rzp-border bg-rzp-gray rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-wide text-gray-500 font-body">Amount</div>
                <div className="font-mono text-rzp-navy font-semibold mt-0.5">{formatINR(detail.amount)}</div>
              </div>
              <div className="border border-rzp-border bg-rzp-gray rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-wide text-gray-500 font-body">Status</div>
                <span className={`inline-block mt-0.5 px-2 py-0.5 rounded border text-[11px] font-mono ${STATUS_STYLE[detail.status]}`}>
                  {STATUS_LABEL[detail.status]}
                </span>
              </div>
              <div className="border border-rzp-border bg-rzp-gray rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-wide text-gray-500 font-body">Decline code</div>
                <div className="font-mono text-rzp-navy font-medium mt-0.5">
                  {detail.decline_code} · {CATEGORY_LABEL[detail.decline_category] || "Not yet diagnosed"}
                </div>
              </div>
              <div className="border border-rzp-border bg-rzp-gray rounded-lg p-3">
                <div className="text-[10px] uppercase tracking-wide text-gray-500 font-body">NPCI attempts used</div>
                <div className="font-mono text-rzp-navy font-medium mt-0.5">{detail.retry_count} / 3</div>
              </div>
              <div className="border border-rzp-border bg-rzp-gray rounded-lg p-3 col-span-2">
                <div className="text-[10px] uppercase tracking-wide text-gray-500 font-body">Merchant / bank</div>
                <div className="font-mono text-rzp-navy font-medium mt-0.5">
                  {detail.mandate.merchant_name} · {detail.mandate.bank_name} · customer for {detail.mandate.subscription_age_days} days
                </div>
              </div>
            </div>

            {/* Demo actions */}
            <div>
              <div className="text-[11px] uppercase tracking-[0.14em] text-gray-500 font-body mb-2">
                Actions
              </div>
              <div className="flex flex-wrap gap-2">
                <ActionButton
                  busy={busyAction === "diagnose"}
                  onClick={() => runAction("diagnose", () => api.diagnose(transactionId))}
                >
                  1. Diagnose
                </ActionButton>
                <ActionButton
                  tone="primary"
                  busy={busyAction === "schedule"}
                  disabled={detail.retry_count >= 3}
                  onClick={() => runAction("schedule", () => api.scheduleRetry(transactionId))}
                >
                  2. Schedule retry
                </ActionButton>
                <ActionButton
                  busy={busyAction === "execute"}
                  onClick={() => runAction("execute", () => api.executeRetry(transactionId))}
                >
                  3. Execute via Razorpay
                </ActionButton>
                <ActionButton
                  tone="danger"
                  busy={busyAction === "cap"}
                  onClick={() => runAction("cap", () => api.scheduleRetry(transactionId))}
                >
                  Try 4th retry (compliance test)
                </ActionButton>
              </div>
              <p className="text-xs text-gray-400 font-body mt-2">
                Diagnose works out why the payment failed. Schedule picks the best retry
                time and follows NPCI's rules automatically. Execute sends the retry to
                the bank. Every step below is logged and tamper-evident.
              </p>
            </div>

            {/* Nudges */}
            {detail.nudges?.length > 0 && (
              <div>
                <div className="text-[11px] uppercase tracking-[0.14em] text-gray-500 font-body mb-2">
                  Customer nudges sent
                </div>
                <div className="space-y-2">
                  {detail.nudges.map((n, i) => (
                    <div key={i} className="border border-rzp-border rounded-lg p-3 bg-rzp-gray">
                      <div className="flex justify-between text-[11px] font-mono text-gray-400 mb-1">
                        <span>{n.channel} {n.simulated ? "(simulated)" : "(live)"}</span>
                        <span>{formatDateTime(n.sent_at)}</span>
                      </div>
                      <div className="text-sm text-gray-700 font-body">{n.message}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Hash-chained audit ledger - the signature element */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <div className="text-[11px] uppercase tracking-[0.14em] text-gray-500 font-body">
                  Audit ledger
                </div>
                {auditTrail && (
                  <span className={`text-[11px] font-mono px-2 py-0.5 rounded border ${
                    auditTrail.chain_valid
                      ? "border-status-success/40 text-status-success"
                      : "border-status-error/40 text-status-error"
                  }`}>
                    {auditTrail.chain_valid ? "hash chain intact" : "chain tampered"}
                  </span>
                )}
              </div>
              <div className="border border-rzp-border rounded-lg bg-rzp-gray text-rzp-navy overflow-hidden">
                {auditTrail?.entries?.length ? (
                  auditTrail.entries.map((entry, i) => (
                    <div key={entry.id} className="flex">
                      <div className="flex flex-col items-center w-8 pt-4">
                        <div className="w-2.5 h-2.5 rounded-full bg-gray-400 shrink-0" />
                        {i < auditTrail.entries.length - 1 && (
                          <div className="chain-link flex-1 bg-transparent" />
                        )}
                      </div>
                      <div className={`flex-1 py-3 pr-4 ${i < auditTrail.entries.length - 1 ? "border-b border-rzp-border" : ""}`}>
                        <div className="flex items-center justify-between">
                          <span className="font-display text-sm font-medium">
                            {STEP_LABEL[entry.step_name] || entry.step_name}
                          </span>
                          <span className="font-mono text-[11px] text-gray-500">
                            {formatDateTime(entry.timestamp)}
                          </span>
                        </div>
                        <div className="font-mono text-[11px] text-gray-500 mt-1 break-all">
                          hash {shortHash(entry.hash)} ← prev {shortHash(entry.prev_hash)}
                        </div>
                        <details className="mt-1.5">
                          <summary className="text-[11px] font-mono text-rzp-blue cursor-pointer hover:underline">
                            payload
                          </summary>
                          <pre className="text-[11px] font-mono text-gray-600 mt-1 whitespace-pre-wrap break-all bg-white border border-rzp-border rounded p-2">
                            {JSON.stringify(JSON.parse(entry.payload_json), null, 2)}
                          </pre>
                        </details>
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="p-4 text-sm text-gray-500 font-body">
                    No audit entries yet — run "Diagnose" above to start the ledger.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
