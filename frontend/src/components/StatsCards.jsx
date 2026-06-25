import React from "react";
import { PhoneCall } from "lucide-react";

export const StatsCards = ({
  calls,
  hotlineNumber = "+91 80 3133 9945",
}) => {
  const totalCalls = calls.length;
  const ordersChecked = calls.filter((call) => call.order_number).length;

  return (
    <div className="stats-grid">
      <div className="stat-card">
        <span className="stat-label">Total Calls</span>
        <span className="stat-value">{totalCalls}</span>
        <span className="stat-desc">All recorded inbound/outbound calls</span>
      </div>

      <div className="stat-card">
        <span className="stat-label">Orders Checked</span>
        <span className="stat-value">{ordersChecked}</span>
        <span className="stat-desc">Calls checking Zoho API order statuses</span>
      </div>

      <div className="stat-card">
        <span className="stat-label">Active Support Line</span>
        <span
          className="stat-value"
          style={{
            fontSize: "1.5rem",
            marginTop: "1.25rem",
            fontFamily: "var(--font-inter)",
            fontWeight: 600,
            color: "var(--accent-primary)",
            display: "flex",
            alignItems: "center",
            gap: "0.5rem",
          }}
        >
          <PhoneCall size={20} strokeWidth={2.5} />
          {hotlineNumber}
        </span>
        <span className="stat-desc" style={{ marginTop: "auto" }}>
          Direct Plivo Hotline
        </span>
      </div>
    </div>
  );
};
