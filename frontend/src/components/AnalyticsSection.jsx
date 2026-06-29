import React, { useState } from "react";
import { TrendingUp, DollarSign } from "lucide-react";

export const AnalyticsSection = ({ calls }) => {
  const [hoveredTrend, setHoveredTrend] = useState(null);

  // --- Aggregate Call Volume for last 7 days ---
  const getTrendData = () => {
    const trendMap = {};
    // Initialize last 7 days
    for (let i = 6; i >= 0; i--) {
      const d = new Date();
      d.setDate(d.getDate() - i);
      const dateStr = d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
      trendMap[dateStr] = 0;
    }

    // Populate counts
    calls.forEach((call) => {
      if (!call.time_of_call) return;
      try {
        const isoStr = call.time_of_call.replace(" ", "T");
        const date = new Date(isoStr);
        if (isNaN(date.getTime())) return;
        const dateStr = date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
        if (trendMap[dateStr] !== undefined) {
          trendMap[dateStr]++;
        }
      } catch (e) {
        // Ignored
      }
    });

    return Object.entries(trendMap).map(([date, count]) => ({ date, count }));
  };

  const trendData = getTrendData();
  const maxCalls = Math.max(...trendData.map((d) => d.count), 5); // Fallback to 5 to avoid flat rendering

  // SVG dimensions for Trend Line
  const svgW = 500;
  const svgH = 150;
  const paddingLeft = 40;
  const paddingRight = 20;
  const paddingTop = 20;
  const paddingBottom = 30;

  const chartW = svgW - paddingLeft - paddingRight;
  const chartH = svgH - paddingTop - paddingBottom;

  // Compute points
  const points = trendData.map((d, index) => {
    const x = paddingLeft + (index * chartW) / (trendData.length - 1);
    const y = svgH - paddingBottom - (d.count / maxCalls) * chartH;
    return { x, y, date: d.date, count: d.count };
  });

  // SVG Path generator
  const linePath = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const areaPath = points.length > 0 
    ? `${linePath} L ${points[points.length - 1].x} ${svgH - paddingBottom} L ${points[0].x} ${svgH - paddingBottom} Z` 
    : "";

  // --- Aggregate Infrastructure Cost ---
  const plivoTotal = calls.reduce((sum, c) => sum + (c.plivo_cost || 0), 0);
  const geminiTotal = calls.reduce((sum, c) => sum + (c.gemini_cost || 0), 0);
  const totalCost = plivoTotal + geminiTotal;

  // Donut chart calculations
  const r = 36;
  const circ = 2 * Math.PI * r; // ~226.19
  const plivoPercent = totalCost > 0 ? (plivoTotal / totalCost) * 100 : 50;
  const geminiPercent = totalCost > 0 ? (geminiTotal / totalCost) * 100 : 50;

  const plivoDash = (plivoPercent / 100) * circ;
  const geminiDash = (geminiPercent / 100) * circ;

  return (
    <div className="analytics-section">
      {/* Call Volume Trend Chart */}
      <div className="chart-card">
        <h3>
          <TrendingUp size={18} strokeWidth={2.5} style={{ color: "var(--accent-primary)" }} />
          Inbound/Outbound Call Volume (Last 7 Days)
        </h3>
        <div className="chart-container">
          <svg viewBox={`0 0 ${svgW} ${svgH}`} width="100%" height="100%">
            <defs>
              <linearGradient id="area-gradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="var(--accent-primary)" stopOpacity="0.25" />
                <stop offset="100%" stopColor="var(--accent-primary)" stopOpacity="0.00" />
              </linearGradient>
            </defs>

            {/* Grid Lines */}
            {[0, 0.25, 0.5, 0.75, 1].map((ratio, i) => {
              const y = paddingTop + ratio * chartH;
              const val = Math.round(maxCalls * (1 - ratio));
              return (
                <g key={i}>
                  <line
                    x1={paddingLeft}
                    y1={y}
                    x2={svgW - paddingRight}
                    y2={y}
                    className="chart-grid-line"
                  />
                  <text x={paddingLeft - 8} y={y + 4} textAnchor="end" className="chart-axis-text">
                    {val}
                  </text>
                </g>
              );
            })}

            {/* Filled Area */}
            {areaPath && <path d={areaPath} className="chart-area" />}

            {/* Stroke Line */}
            {linePath && <path d={linePath} className="chart-line" />}

            {/* Data Dots & Hover Overlay */}
            {points.map((p, i) => (
              <g key={i}>
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={hoveredTrend?.index === i ? 6 : 4.5}
                  className="chart-dot"
                  onMouseEnter={() => setHoveredTrend({ ...p, index: i })}
                  onMouseLeave={() => setHoveredTrend(null)}
                />
              </g>
            ))}

            {/* X Axis Labels */}
            {points.map((p, i) => (
              <text
                key={i}
                x={p.x}
                y={svgH - 8}
                textAnchor="middle"
                className="chart-axis-text"
                style={{ fontWeight: 500 }}
              >
                {p.date}
              </text>
            ))}

            {/* Hover Tooltip Overlay in SVG */}
            {hoveredTrend && (
              <g>
                <rect
                  x={hoveredTrend.x - 45}
                  y={hoveredTrend.y - 32}
                  width="90"
                  height="22"
                  rx="4"
                  fill="var(--text-primary)"
                  opacity="0.9"
                />
                <text
                  x={hoveredTrend.x}
                  y={hoveredTrend.y - 17}
                  fill="var(--bg-color)"
                  fontSize="9.5px"
                  fontWeight="600"
                  textAnchor="middle"
                  fontFamily="var(--font-inter)"
                >
                  {hoveredTrend.count} call{hoveredTrend.count !== 1 ? "s" : ""}
                </text>
              </g>
            )}
          </svg>
        </div>
      </div>

      {/* Cost Breakdown Donut Chart */}
      <div className="chart-card">
        <h3>
          <DollarSign size={18} strokeWidth={2.5} style={{ color: "var(--success)" }} />
          Infrastructure Cost
        </h3>
        <div 
          className="chart-container" 
          style={{ 
            display: "grid", 
            gridTemplateColumns: "1.2fr 1fr",
            alignItems: "center"
          }}
        >
          {/* Donut SVG */}
          <div style={{ position: "relative", width: "100%", height: "100%", display: "flex", justifyContent: "center" }}>
            <svg viewBox="0 0 100 100" width="130" height="130">
              {/* Background ring */}
              <circle
                cx="50"
                cy="50"
                r={r}
                fill="none"
                stroke="var(--border-color)"
                strokeWidth="10"
              />

              {/* Plivo Segment */}
              <circle
                cx="50"
                cy="50"
                r={r}
                fill="none"
                stroke="var(--accent-primary)"
                strokeWidth="10"
                className="chart-donut-segment"
                strokeDasharray={`${plivoDash} ${circ}`}
                strokeDashoffset="0"
                transform="rotate(-90 50 50)"
              />

              {/* Gemini Segment */}
              <circle
                cx="50"
                cy="50"
                r={r}
                fill="none"
                stroke="var(--success)"
                strokeWidth="10"
                className="chart-donut-segment"
                strokeDasharray={`${geminiDash} ${circ}`}
                strokeDashoffset={-plivoDash}
                transform="rotate(-90 50 50)"
              />

              {/* Center Text */}
              <g className="donut-center-text">
                <text y="46" className="donut-val">
                  ${totalCost.toFixed(2)}
                </text>
                <text y="62" className="donut-lbl">
                  TOTAL COST
                </text>
              </g>
            </svg>
          </div>

          {/* Donut Legend */}
          <div className="donut-legend">
            <div className="legend-item">
              <span className="legend-color" style={{ backgroundColor: "var(--accent-primary)" }} />
              <span className="legend-lbl">Plivo SDK</span>
              <span className="legend-val">${plivoTotal.toFixed(2)}</span>
            </div>
            <div className="legend-item">
              <span className="legend-color" style={{ backgroundColor: "var(--success)" }} />
              <span className="legend-lbl">Gemini LLM</span>
              <span className="legend-val">${geminiTotal.toFixed(2)}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
