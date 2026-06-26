import React, { useState, useEffect } from "react";
import { 
  Phone, 
  MessageSquare, 
  ArrowUpDown, 
  ArrowUp, 
  ArrowDown, 
  Filter
} from "lucide-react";

export const CallsTable = ({
  calls,
  lastUpdated,
  onOpenTranscript,
  onInitiateCallback,
}) => {
  // Sort State
  const [sortKey, setSortKey] = useState("time_of_call");
  const [sortOrder, setSortOrder] = useState("desc"); // 'asc' | 'desc'

  // Filter State
  const [typeFilter, setTypeFilter] = useState("all"); // 'all' | 'direct' | 'forwarded'
  const [orderFilter, setOrderFilter] = useState("all"); // 'all' | 'with-order' | 'no-order'

  // Pagination State
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  // Reset page when filters change
  useEffect(() => {
    setCurrentPage(1);
  }, [typeFilter, orderFilter]);

  // Duration formatting helper
  const formatDuration = (seconds) => {
    if (!seconds || seconds <= 0) return "0s";
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    if (mins > 0) {
      return `${mins}m ${secs}s`;
    }
    return `${secs}s`;
  };

  // Timestamp formatting helper
  const formatCallTime = (timestampStr) => {
    if (!timestampStr) return "N/A";
    try {
      const isoStr = timestampStr.replace(" ", "T");
      const date = new Date(isoStr);
      if (isNaN(date.getTime())) return timestampStr;

      return date.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
        hour12: true,
      });
    } catch (e) {
      return timestampStr;
    }
  };

  // Handle header sort triggers
  const handleSort = (key) => {
    if (sortKey === key) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortOrder("desc"); // Default to desc for new keys
    }
  };

  // Render Sort Header Indicator
  const renderSortIndicator = (key) => {
    if (sortKey !== key) return <ArrowUpDown size={12} style={{ marginLeft: "4px", opacity: 0.4 }} />;
    return sortOrder === "asc" ? (
      <ArrowUp size={12} style={{ marginLeft: "4px", color: "var(--accent-primary)" }} />
    ) : (
      <ArrowDown size={12} style={{ marginLeft: "4px", color: "var(--accent-primary)" }} />
    );
  };

  // 1. Apply dropdown filters
  const filteredCalls = calls.filter((call) => {
    // Type Filter
    if (typeFilter === "direct" && call.call_forwarded) return false;
    if (typeFilter === "forwarded" && !call.call_forwarded) return false;

    // Order ID Filter
    const hasOrder = !!call.order_number;
    if (orderFilter === "with-order" && !hasOrder) return false;
    if (orderFilter === "no-order" && hasOrder) return false;

    return true;
  });

  // 2. Apply sorting
  const sortedCalls = [...filteredCalls].sort((a, b) => {
    let valA = a[sortKey];
    let valB = b[sortKey];

    // Fallbacks and parsing
    if (sortKey === "total_cost") {
      valA = a.total_cost ?? 0;
      valB = b.total_cost ?? 0;
    } else if (sortKey === "duration") {
      valA = a.duration ?? 0;
      valB = b.duration ?? 0;
    } else if (sortKey === "phone_number") {
      valA = (a.phone_number || "").toLowerCase();
      valB = (b.phone_number || "").toLowerCase();
    } else if (sortKey === "time_of_call") {
      valA = a.time_of_call ? new Date(a.time_of_call.replace(" ", "T")).getTime() : 0;
      valB = b.time_of_call ? new Date(b.time_of_call.replace(" ", "T")).getTime() : 0;
    }

    if (valA < valB) return sortOrder === "asc" ? -1 : 1;
    if (valA > valB) return sortOrder === "asc" ? 1 : -1;
    return 0;
  });

  // 3. Paginate slice
  const totalItems = sortedCalls.length;
  const totalPages = Math.max(Math.ceil(totalItems / itemsPerPage), 1);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const endIndex = Math.min(startIndex + itemsPerPage, totalItems);
  const paginatedCalls = sortedCalls.slice(startIndex, endIndex);

  return (
    <div className="table-card">
      <div className="table-header" style={{ flexWrap: "wrap", gap: "1rem" }}>
        <div className="table-title">
          Recent Conversations
          <span className="table-subtitle">({totalItems} matched)</span>
        </div>

        {/* Filter Controls Row */}
        <div style={{ display: "flex", gap: "0.75rem", alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", fontSize: "0.8rem", color: "var(--text-secondary)" }}>
            <Filter size={12} />
            <span>Filters:</span>
          </div>

          {/* Call Type Dropdown */}
          <select 
            className="filter-select"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            style={{ padding: "0.4rem 0.75rem", fontSize: "0.8rem" }}
          >
            <option value="all">All Types</option>
            <option value="direct">Direct Only</option>
            <option value="forwarded">Forwarded Only</option>
          </select>

          {/* Order Status Dropdown */}
          <select 
            className="filter-select"
            value={orderFilter}
            onChange={(e) => setOrderFilter(e.target.value)}
            style={{ padding: "0.4rem 0.75rem", fontSize: "0.8rem" }}
          >
            <option value="all">All Orders</option>
            <option value="with-order">With Order ID</option>
            <option value="no-order">Without Order ID</option>
          </select>

          <span
            style={{
              fontSize: "0.8rem",
              color: "var(--text-secondary)",
              fontWeight: "normal",
              marginLeft: "0.5rem"
            }}
          >
            {lastUpdated}
          </span>
        </div>
      </div>

      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th className="sortable" onClick={() => handleSort("phone_number")}>
                Phone Number {renderSortIndicator("phone_number")}
              </th>
              <th className="sortable" onClick={() => handleSort("time_of_call")}>
                Time of Call {renderSortIndicator("time_of_call")}
              </th>
              <th>Order ID</th>
              <th className="sortable" onClick={() => handleSort("duration")}>
                Duration {renderSortIndicator("duration")}
              </th>
              <th className="sortable" onClick={() => handleSort("total_cost")}>
                Cost {renderSortIndicator("total_cost")}
              </th>
              <th>Forwarding</th>
              <th>Transcription</th>
              <th>Forwarded Transcript</th>
            </tr>
          </thead>
          <tbody>
            {paginatedCalls.length === 0 ? (
              <tr>
                <td colSpan={8} className="empty-state">
                  <MessageSquare size={48} />
                  <p>No conversations matched the selected filters.</p>
                </td>
              </tr>
            ) : (
              paginatedCalls.map((call) => {
                const hasTranscript = call.transcript && call.transcript.length > 0;

                return (
                  <tr key={call.id}>
                    <td>
                      <div className="phone-num">
                        <Phone size={14} strokeWidth={2.5} />
                        <span>{call.phone_number || "Unknown"}</span>
                      </div>
                    </td>
                    <td className="time-cell">{formatCallTime(call.time_of_call)}</td>
                    <td>
                      {call.order_number ? (
                        <span className="badge badge-indigo">{call.order_number}</span>
                      ) : (
                        <span className="badge badge-gray">—</span>
                      )}
                    </td>
                    <td className="time-cell">{formatDuration(call.duration)}</td>
                    <td>
                      <div style={{ display: "flex", flexDirection: "column" }}>
                        <span style={{ fontWeight: 600, color: "var(--text-primary)", fontSize: "0.9rem" }}>
                          ${(call.total_cost ?? 0).toFixed(2)}
                        </span>
                        <span style={{ fontSize: "0.72rem", color: "var(--text-secondary)", whiteSpace: "nowrap" }} title="Plivo / Gemini Live">
                          P: ${(call.plivo_cost ?? 0).toFixed(2)} | G: ${(call.gemini_cost ?? 0).toFixed(2)}
                        </span>
                      </div>
                    </td>
                    <td>
                      {call.call_forwarded ? (
                        <span
                          className="badge"
                          style={{
                            backgroundColor: "var(--warning-bg)",
                            color: "var(--warning-text)",
                            border: "1px solid var(--warning-border)",
                          }}
                        >
                          Forwarded
                        </span>
                      ) : (
                        <span className="badge badge-gray">Direct</span>
                      )}
                    </td>
                    <td>
                      {hasTranscript ? (
                        <button
                          className="btn btn-outline"
                          style={{
                            padding: "0.35rem 0.75rem",
                            fontSize: "0.8rem",
                            borderRadius: "6px",
                          }}
                          onClick={() => onOpenTranscript(call, "standard")}
                        >
                          <MessageSquare
                            size={12}
                            strokeWidth={2.5}
                            style={{ marginRight: "2px" }}
                          />
                          View ({call.transcript.length})
                        </button>
                      ) : (
                        <span
                          style={{
                            color: "var(--text-secondary)",
                            fontStyle: "italic",
                            fontSize: "0.8rem",
                          }}
                        >
                          Empty
                        </span>
                      )}
                    </td>
                    <td>
                      {call.call_forwarded ? (
                        <button
                          className="btn btn-outline"
                          style={{
                            padding: "0.35rem 0.75rem",
                            fontSize: "0.8rem",
                            borderRadius: "6px",
                            borderColor: "var(--warning-text)",
                            color: "var(--warning-text)",
                          }}
                          onClick={() => onOpenTranscript(call, "forwarded")}
                        >
                          <MessageSquare
                            size={12}
                            strokeWidth={2.5}
                            style={{ marginRight: "2px" }}
                          />
                          View Forwarded
                        </button>
                      ) : (
                        <span
                          style={{
                            color: "var(--text-secondary)",
                            fontStyle: "italic",
                            fontSize: "0.8rem",
                          }}
                        >
                          —
                        </span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Controls Footer */}
      {totalItems > 0 && (
        <div className="pagination-container">
          <div className="pagination-info">
            Showing {startIndex + 1} to {endIndex} of {totalItems} entries
          </div>
          <div className="pagination-controls">
            <button
              className="page-btn"
              onClick={() => setCurrentPage(currentPage - 1)}
              disabled={currentPage === 1}
            >
              Previous
            </button>
            
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
              <button
                key={page}
                className={`page-btn ${currentPage === page ? "active" : ""}`}
                onClick={() => setCurrentPage(page)}
              >
                {page}
              </button>
            ))}

            <button
              className="page-btn"
              onClick={() => setCurrentPage(currentPage + 1)}
              disabled={currentPage === totalPages}
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

