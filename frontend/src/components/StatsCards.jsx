import React from "react";
import { Phone, ShoppingBag, Zap } from "lucide-react";

export const StatsCards = ({ calls }) => {
  const totalCalls = calls.length;
  const ordersChecked = calls.filter((call) => call.order_number).length;
  const totalCost = calls.reduce(
    (sum, call) => sum + (call.total_cost || 0),
    0,
  );

  const stats = [
    {
      icon: Phone,
      label: "Total Calls",
      value: totalCalls,
      desc: "All recorded inbound calls",
      iconBg: "rgba(79,70,229,0.1)",
      iconColor: "var(--accent-primary)",
      accentBar: "var(--accent-primary)",
    },
    {
      icon: ShoppingBag,
      label: "Orders Checked",
      value: ordersChecked,
      desc: "Calls that queried Zoho order statuses",
      iconBg: "rgba(16,185,129,0.1)",
      iconColor: "var(--success)",
      accentBar: "var(--success)",
    },
    {
      icon: Zap,
      label: "Infrastructure Cost",
      value: `$${totalCost.toFixed(2)}`,
      desc: "Accumulated Plivo + Gemini API usage",
      iconBg: "rgba(245,158,11,0.1)",
      iconColor: "#d97706",
      accentBar: "#f59e0b",
    },
  ];

  return (
    <div className="stats-grid">
      {stats.map(
        ({ icon: Icon, label, value, desc, iconBg, iconColor, accentBar }) => (
          <div className="stat-card" key={label}>
            <div className="stat-card-inner">
              <div
                className="stat-icon-wrap"
                style={{ background: iconBg, color: iconColor }}
              >
                <Icon size={18} strokeWidth={2.2} />
              </div>
              <div className="stat-content">
                <span className="stat-label">{label}</span>
                <span className="stat-value">{value}</span>
                <span className="stat-desc">{desc}</span>
              </div>
            </div>
          </div>
        ),
      )}
    </div>
  );
};
