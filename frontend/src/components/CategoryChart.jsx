import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
} from "recharts";
import { CATEGORY_LABEL, CATEGORY_COLOR, formatINR } from "../utils";

export default function CategoryChart({ summary }) {
  if (!summary) return null;

  const data = Object.entries(summary.by_category).map(([key, val]) => ({
    key,
    label: CATEGORY_LABEL[key] || key,
    amount: val.amount,
    count: val.count,
  }));

  return (
    <div className="border border-paper-100/10 rounded-lg bg-ink-800/60 p-5 h-full">
      <div className="text-[11px] uppercase tracking-[0.14em] text-paper-100/50 font-body mb-3">
        Amount at risk by root cause
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="label"
            width={130}
            tick={{ fill: "#F6F3ECB3", fontSize: 12, fontFamily: "IBM Plex Sans" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "rgba(246,243,236,0.05)" }}
            contentStyle={{
              background: "#0B1F3A",
              border: "1px solid rgba(246,243,236,0.15)",
              borderRadius: 8,
              fontFamily: "IBM Plex Mono",
              fontSize: 12,
            }}
            formatter={(value, name, props) => [
              `${formatINR(value)} · ${props.payload.count} txns`,
              "At risk",
            ]}
          />
          <Bar dataKey="amount" radius={[0, 4, 4, 0]} barSize={18}>
            {data.map((d) => (
              <Cell key={d.key} fill={CATEGORY_COLOR[d.key]} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
