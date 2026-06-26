import React, { useState } from "react";
import {
  PhoneCall,
  Phone,
  Play,
  Loader,
  Check,
  AlertCircle,
} from "lucide-react";

export const StatsCards = ({
  calls,
  hotlineNumber = "+91 80 3133 9945",
  onDial,
  callbackNumber,
}) => {
  const totalCalls = calls.length;
  const ordersChecked = calls.filter((call) => call.order_number).length;
  const totalCost = calls.reduce(
    (sum, call) => sum + (call.total_cost || 0),
    0,
  );

  // Dialer State
  const [customerNumber, setCustomerNumber] = useState("");
  const [dialStatus, setDialStatus] = useState(null); // 'calling', 'success', 'error'
  const [statusMsg, setStatusMsg] = useState("");

  // Populate dialer when callback clicked
  React.useEffect(() => {
    if (callbackNumber) {
      setCustomerNumber(callbackNumber);
    }
  }, [callbackNumber]);

  const handleDial = async (e) => {
    e.preventDefault();
    const formattedNum = customerNumber.trim();
    if (!formattedNum) return;

    // Optional basic check for E.164 (must start with +)
    if (!formattedNum.startsWith("+")) {
      setDialStatus("error");
      setStatusMsg("Number must start with '+' (e.g. +91...)");
      setTimeout(() => {
        setDialStatus(null);
        setStatusMsg("");
      }, 4000);
      return;
    }

    setDialStatus("calling");
    setStatusMsg("Dialing Plivo Hotline...");

    try {
      const res = await onDial(formattedNum);
      if (res && res.success) {
        setDialStatus("success");
        setStatusMsg(res.message || "Outbound call initiated!");
        setCustomerNumber("");
      } else {
        setDialStatus("error");
        setStatusMsg(res?.message || "Outbound call failed.");
      }
    } catch (err) {
      setDialStatus("error");
      setStatusMsg(err.message || "Request failed.");
    }

    setTimeout(() => {
      setDialStatus(null);
      setStatusMsg("");
    }, 5000);
  };

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
        <span className="stat-desc">
          Calls checking Zoho API order statuses
        </span>
      </div>

      <div className="stat-card">
        <span className="stat-label">Total Infrastructure Cost</span>
        <span className="stat-value">${totalCost.toFixed(2)}</span>
        <span className="stat-desc">Accumulated Plivo + Gemini API usage</span>
      </div>

      <div className="stat-card" style={{ paddingBottom: "1.25rem" }}>
        <span className="stat-label">Active Support Line</span>
        <span
          className="stat-value"
          style={{
            fontSize: "1.5rem",
            marginTop: "0.5rem",
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
      </div>
    </div>
  );
};
