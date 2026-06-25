import React from "react";
import { Phone, MessageSquare } from "lucide-react";

export const CallsTable = ({
  calls,
  lastUpdated,
  onOpenTranscript,
}) => {
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

  return (
    <div className="table-card">
      <div className="table-header">
        <span>Recent Conversations</span>
        <span
          style={{
            fontSize: "0.85rem",
            color: "var(--text-secondary)",
            fontWeight: "normal",
          }}
        >
          {lastUpdated}
        </span>
      </div>
      <div className="table-wrapper">
        <table>
          <thead>
            <tr>
              <th>Phone Number</th>
              <th>Time of Call</th>
              <th>Order ID</th>
              <th>Duration</th>
              <th>Forwarding</th>
              <th>Transcription</th>
              <th>Forwarded Transcript</th>
            </tr>
          </thead>
          <tbody>
            {calls.length === 0 ? (
              <tr>
                <td colSpan={7} className="empty-state">
                  <MessageSquare size={48} style={{ color: "#cbd5e1", marginBottom: "1rem" }} />
                  <p>No conversations matched the filter or have been logged yet.</p>
                </td>
              </tr>
            ) : (
              calls.map((call) => {
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
                        <span className="badge badge-cyan">{call.order_number}</span>
                      ) : (
                        <span className="badge badge-gray">—</span>
                      )}
                    </td>
                    <td className="time-cell">{formatDuration(call.duration)}</td>
                    <td>
                      {call.call_forwarded ? (
                        <span
                          className="badge"
                          style={{
                            backgroundColor: "#fef3c7",
                            color: "#d97706",
                            border: "1px solid #fde68a",
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
                            borderRadius: "4px",
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
                            borderRadius: "4px",
                            borderColor: "#d97706",
                            color: "#d97706",
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
    </div>
  );
};
