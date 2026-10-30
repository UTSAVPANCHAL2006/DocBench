import { f1, NAMES, type Headline, type Pipeline } from "@/lib/data";

/** Critical-field accuracy (x) against silent critical errors (y), drawn to scale. */
export function Scatter({ headline }: { headline: Headline[] }) {
  const W = 640, H = 400, m = { l: 58, r: 24, t: 18, b: 52 };
  // The y range starts below zero so points with only a handful of silent errors sit clear of the axis.
  const X0 = 40, X1 = 100;
  const Ymax = Math.ceil(Math.max(...headline.map(h => h.critical_silent)) / 40) * 40, Ymin = -Ymax * 0.1;
  const x = (v: number) => m.l + (v - X0) / (X1 - X0) * (W - m.l - m.r);
  const y = (v: number) => H - m.b - (v - Ymin) / (Ymax - Ymin) * (H - m.t - m.b);
  const yMid = (y(Ymax) + y(Ymin)) / 2;
  const v1 = headline.find(h => h.pipeline === "vision_llm")!;
  const v2 = headline.find(h => h.pipeline === "vision_verified")!;
  // Points near the bottom carry their labels above them; the rest beside them.
  const place: Record<Pipeline, ["start" | "middle" | "end", number, "side" | "above"]> = {
    ocr_regex: ["start", 13, "side"], ocr_text_llm: ["start", 13, "side"], vision_llm: ["end", -13, "side"],
    ocr_reference: ["middle", 0, "above"], vision_verified: ["end", -14, "above"],
  };
  const xTicks = Array.from({ length: (X1 - X0) / 10 + 1 }, (_, i) => X0 + i * 10);
  const yTicks = Array.from({ length: Ymax / 40 + 1 }, (_, i) => i * 40);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Scatter plot of critical-field accuracy against silent critical errors for five pipelines">
      <defs>
        <marker id="arr" viewBox="0 0 10 10" refX="8" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
          <path d="M0,0 L10,5 L0,10 z" fill="var(--accent)" />
        </marker>
      </defs>
      {xTicks.map(v => (
        <g key={`x${v}`}>
          <line className="grid" x1={x(v)} x2={x(v)} y1={y(Ymin)} y2={y(Ymax)} />
          <text x={x(v)} y={y(Ymin) + 20} textAnchor="middle">{v}%</text>
        </g>
      ))}
      {yTicks.map(v => (
        <g key={`y${v}`}>
          <line className={v === 0 ? "grid zero" : "grid"} x1={x(X0)} x2={x(X1)} y1={y(v)} y2={y(v)} />
          <text x={m.l - 12} y={y(v) + 4} textAnchor="end">{v}</text>
        </g>
      ))}
      <text className="axis-title" x={(m.l + W - m.r) / 2} y={H - 8} textAnchor="middle">Critical-field accuracy</text>
      <text className="axis-title" x={16} y={yMid} textAnchor="middle" transform={`rotate(-90 16 ${yMid})`}>Silent critical errors</text>
      <path className="drop" markerEnd="url(#arr)"
        d={`M${x(v1.critical_acc)},${y(v1.critical_silent) + 10} L${x(v2.critical_acc)},${y(v2.critical_silent) - 12}`} />
      <text className="drop-label" x={x(v1.critical_acc) - 12} y={y(v1.critical_silent) + 36} textAnchor="end">
        −{v1.critical_silent - v2.critical_silent} with validation
      </text>
      {headline.map(h => {
        const px = x(h.critical_acc), py = y(h.critical_silent), hi = h.pipeline === "vision_verified";
        const [anchor, dx, pos] = place[h.pipeline];
        const [ly, sy] = pos === "above" ? [py - 30, py - 15] : [py - 2, py + 13];
        return (
          <g key={h.pipeline}>
            <text className="pt-label" x={px + dx} y={ly} textAnchor={anchor}>{NAMES[h.pipeline][0]}</text>
            <text className="pt-sub" x={px + dx} y={sy} textAnchor={anchor}>{f1(h.critical_acc)}% · {h.critical_silent}</text>
            <circle cx={px} cy={py} r={hi ? 7 : 5.5} fill={hi ? "var(--accent)" : "var(--surface)"}
              stroke={hi ? "var(--accent)" : "var(--ink)"} strokeWidth={2} />
          </g>
        );
      })}
    </svg>
  );
}

/** Pipelines (rows) by condition or document type (columns), shaded by accuracy. */
export function Heat({ headline, cols, labels, matrix }: {
  headline: Headline[]; cols: string[]; labels: Record<string, string>; matrix: Record<Pipeline, number[]>;
}) {
  return (
    <table className="heat">
      <thead>
        <tr><th scope="col" />{cols.map(c => <th scope="col" key={c}>{labels[c]}</th>)}</tr>
      </thead>
      <tbody>
        {headline.map(h => (
          <tr key={h.pipeline}>
            <td className="lab">{NAMES[h.pipeline][0]}</td>
            {matrix[h.pipeline].map((v, i) => {
              const a = Math.max(0.06, Math.pow(v / 100, 2.2) * 0.92);
              return (
                <td key={cols[i]} className={`cell num${a > 0.5 ? " dark" : ""}`} style={{ ["--a" as string]: a.toFixed(3) }}>
                  {Math.round(v)}%
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
