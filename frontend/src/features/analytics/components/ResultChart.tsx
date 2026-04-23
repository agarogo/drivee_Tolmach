import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { QueryResult } from "../../../shared/types";
import { deriveSemanticVisualization, getSnapshotRows } from "../lib/queryPresentation";

const COLORS = ["#6cff72", "#3db842", "#f5a623", "#6bb8ff"];

export function ResultChart({ query }: { query: QueryResult }) {
  const rows = getSnapshotRows(query);
  const visualization = deriveSemanticVisualization(query);

  if (!rows.length) {
    return <div className="empty-card">Backend returned no rows, so there is nothing to visualize.</div>;
  }

  if (visualization.chartType === "table_only" || !visualization.xKey || !visualization.series.length) {
    return (
      <div className="empty-card">
        <strong>Table-first result</strong>
        <span>{visualization.reason}</span>
      </div>
    );
  }

  return (
    <div className="chart-card">
      <div className="chart-meta">
        <strong>{visualization.chartType === "line" ? "Line chart" : "Bar chart"}</strong>
        <span>{visualization.reason}</span>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        {visualization.chartType === "line" ? (
          <LineChart data={rows}>
            <CartesianGrid stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey={visualization.xKey} stroke="#556059" />
            <YAxis stroke="#556059" />
            <Tooltip contentStyle={{ background: "#1e2326", border: "1px solid rgba(255,255,255,0.12)", color: "#f0f2f1" }} />
            <Legend />
            {visualization.series.map((item, index) => (
              <Line
                key={item.key}
                type="monotone"
                dataKey={item.key}
                name={item.name}
                stroke={COLORS[index % COLORS.length]}
                strokeWidth={2}
                dot={false}
              />
            ))}
          </LineChart>
        ) : (
          <BarChart data={rows}>
            <CartesianGrid stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey={visualization.xKey} stroke="#556059" />
            <YAxis stroke="#556059" />
            <Tooltip contentStyle={{ background: "#1e2326", border: "1px solid rgba(255,255,255,0.12)", color: "#f0f2f1" }} />
            <Legend />
            {visualization.series.map((item, index) => (
              <Bar
                key={item.key}
                dataKey={item.key}
                name={item.name}
                fill={COLORS[index % COLORS.length]}
                radius={[4, 4, 0, 0]}
              />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
