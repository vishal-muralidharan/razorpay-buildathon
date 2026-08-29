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
    <div className="border border-rzp-border rounded-lg bg-white shadow-sm p-5 h-full">
      <div className="text-[11px] uppercase tracking-[0.14em] text-gray-500 font-body mb-3">
        Amount at risk by root cause
      </div>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
          <XAxis type="number" hide />
          <YAxis
            type="category"
            dataKey="label"
            width={130}
            tick={{ fill: "#4B5563", fontSize: 12, fontFamily: "Inter" }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "rgba(1,38,82,0.05)" }}
            contentStyle={{
              background: "#FFFFFF",
              border: "1px solid #E2E8F0",
              borderRadius: 8,
              fontFamily: "Inter",
              fontSize: 12,
              color: "#012652"
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
