import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { QueryResultRow } from "../../../../shared/types";

const CHART_COLORS = [
  "#6cff72",
  "#3db842",
  "#7fdc80",
  "#f7d154",
  "#69b8ff",
  "#ff8c5a",
  "#d7f871",
];

function browserOnlyFallback(label: string) {
  return (
    <div className="answer-chart-fallback">
      <strong>{label}</strong>
      <span>Chart preview is available in the browser runtime.</span>
    </div>
  );
}

function chartTooltipStyle() {
  return {
    background: "#10171a",
    border: "1px solid rgba(255,255,255,0.08)",
    borderRadius: "12px",
    color: "#f0f2f1",
    boxShadow: "0 16px 48px rgba(0,0,0,0.22)",
  };
}

export function RankingBarChart({
  data,
  xKey,
  barKey,
  label,
}: {
  data: QueryResultRow[];
  xKey: string;
  barKey: string;
  label: string;
}) {
  if (typeof window === "undefined") return browserOnlyFallback("Ranking chart");

  return (
    <div className="answer-chart-card answer-chart-card--wide">
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={data} layout="vertical" margin={{ left: 18, right: 18, top: 12, bottom: 12 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.05)" horizontal={false} />
          <XAxis type="number" stroke="#70807a" />
          <YAxis dataKey={xKey} type="category" width={110} stroke="#70807a" />
          <Tooltip contentStyle={chartTooltipStyle()} cursor={{ fill: "rgba(108,255,114,0.08)" }} />
          <Legend />
          <Bar dataKey={barKey} name={label} fill={CHART_COLORS[0]} radius={[0, 10, 10, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

export function TrendLineChart({
  data,
  xKey,
  lineKey,
  label,
}: {
  data: QueryResultRow[];
  xKey: string;
  lineKey: string;
  label: string;
}) {
  if (typeof window === "undefined") return browserOnlyFallback("Trend chart");

  return (
    <div className="answer-chart-card answer-chart-card--wide">
      <ResponsiveContainer width="100%" height={340}>
        <LineChart data={data} margin={{ left: 18, right: 18, top: 12, bottom: 12 }}>
          <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
          <XAxis dataKey={xKey} stroke="#70807a" />
          <YAxis stroke="#70807a" />
          <Tooltip contentStyle={chartTooltipStyle()} cursor={{ stroke: "#6cff72", strokeOpacity: 0.2 }} />
          <Legend />
          <Line
            type="monotone"
            dataKey={lineKey}
            name={label}
            stroke={CHART_COLORS[0]}
            strokeWidth={3}
            dot={{ r: 3, fill: CHART_COLORS[0], strokeWidth: 0 }}
            activeDot={{ r: 5 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

export function DistributionDonutChart({
  data,
  labelKey,
  valueKey,
}: {
  data: QueryResultRow[];
  labelKey: string;
  valueKey: string;
}) {
  if (typeof window === "undefined") return browserOnlyFallback("Distribution chart");

  return (
    <div className="answer-chart-card answer-chart-card--donut">
      <ResponsiveContainer width="100%" height={320}>
        <PieChart>
          <Tooltip contentStyle={chartTooltipStyle()} />
          <Legend />
          <Pie
            data={data}
            dataKey={valueKey}
            nameKey={labelKey}
            innerRadius={72}
            outerRadius={112}
            paddingAngle={3}
            stroke="rgba(255,255,255,0.06)"
            strokeWidth={1}
          >
            {data.map((_, index) => (
              <Cell key={`${labelKey}-${index}`} fill={CHART_COLORS[index % CHART_COLORS.length]} />
            ))}
          </Pie>
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
