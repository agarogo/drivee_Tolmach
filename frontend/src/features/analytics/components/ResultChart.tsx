import { Bar, BarChart, CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

export function ResultChart({ rows, chartSpec }: { rows: Array<Record<string, any>>; chartSpec: Record<string, any> }) {
  if (!rows.length || !chartSpec || chartSpec.type === "table_only") {
    return <div className="empty-card">Для этого результата таблица информативнее графика.</div>;
  }
  const x = chartSpec.x || Object.keys(rows[0])[0];
  const series = chartSpec.series || [{ key: Object.keys(rows[0]).find((key) => typeof rows[0][key] === "number"), name: "value" }];
  const colors = ["#6cff72", "#3db842", "#f5a623", "#8b9490"];
  return (
    <div className="chart-card">
      <ResponsiveContainer width="100%" height={300}>
        {chartSpec.type === "line" ? (
          <LineChart data={rows}>
            <CartesianGrid stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey={x} stroke="#556059" />
            <YAxis stroke="#556059" />
            <Tooltip contentStyle={{ background: "#1e2326", border: "1px solid rgba(255,255,255,0.12)", color: "#f0f2f1" }} />
            <Legend />
            {series.map((item: any, index: number) => (
              <Line key={item.key} type="monotone" dataKey={item.key} stroke={colors[index % colors.length]} strokeWidth={2} dot={false} />
            ))}
          </LineChart>
        ) : (
          <BarChart data={rows}>
            <CartesianGrid stroke="rgba(255,255,255,0.05)" />
            <XAxis dataKey={x} stroke="#556059" />
            <YAxis stroke="#556059" />
            <Tooltip contentStyle={{ background: "#1e2326", border: "1px solid rgba(255,255,255,0.12)", color: "#f0f2f1" }} />
            <Legend />
            {series.map((item: any, index: number) => (
              <Bar key={item.key} dataKey={item.key} fill={colors[index % colors.length]} radius={[4, 4, 0, 0]} />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}
