import React from "react";
import { Phone, ShoppingBag, Zap, Wallet } from "lucide-react";

export const StatsCards = ({ calls = [], stats, balance }) => {
  const totalCalls = (stats && typeof stats.total_calls === "number") ? stats.total_calls : calls.length;
  const ordersChecked = (stats && typeof stats.orders_checked === "number") ? stats.orders_checked : calls.filter((call) => call.order_number).length;
  const totalCost = (stats && typeof stats.total_cost === "number") ? stats.total_cost : calls.reduce(
    (sum, call) => sum + (call.total_cost || 0),
    0,
  );

  const plivoBalance = balance && typeof balance.balance === "number"
    ? `$${balance.balance.toFixed(2)}`
    : "—";

  const cardItems = [
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
    {
      icon: Wallet,
      label: "Plivo Balance",
      value: plivoBalance,
      desc: "Current Plivo account credit",
      iconBg: "rgba(99,102,241,0.1)",
      iconColor: "#6366f1",
      accentBar: "#6366f1",
    },
  ];

  return (
    <div className="stats-grid">
      {cardItems.map(
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
