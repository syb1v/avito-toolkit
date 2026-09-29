"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { DailyPoint } from "@/lib/api";
import { formatCompact, formatPrice } from "@/lib/format";

export function PriceChart({ data }: { data: DailyPoint[] }) {
  const points = data.filter((point) => point.price_median !== null);
  if (points.length === 0) {
    return (
      <p className="px-5 py-10 text-sm text-neutral-500">
        История цен появится после обходов: снапшоты пишутся при первом появлении
        объявления и при каждой смене цены.
      </p>
    );
  }
  return (
    <div className="h-72 w-full px-2 py-4">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={points} margin={{ top: 8, right: 16, bottom: 0, left: 8 }}>
          <CartesianGrid stroke="#262626" strokeDasharray="3 3" />
          <XAxis dataKey="calc_date" stroke="#737373" fontSize={12} tickLine={false} />
          <YAxis
            stroke="#737373"
            fontSize={12}
            tickLine={false}
            width={64}
            tickFormatter={(value) => formatCompact(Number(value))}
          />
          <Tooltip
            contentStyle={{
              background: "#171717",
              border: "1px solid #404040",
              borderRadius: 8,
            }}
            labelStyle={{ color: "#a3a3a3" }}
            formatter={(value) => formatPrice(Number(value))}
          />
          <Line
            type="monotone"
            dataKey="price_median"
            name="Медиана"
            stroke="#34d399"
            strokeWidth={2}
            dot={false}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="price_p25"
            name="P25"
            stroke="#60a5fa"
            strokeWidth={1.5}
            dot={false}
            connectNulls
          />
          <Line
            type="monotone"
            dataKey="price_p75"
            name="P75"
            stroke="#f59e0b"
            strokeWidth={1.5}
            dot={false}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
