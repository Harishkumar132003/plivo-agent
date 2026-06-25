import React from "react";
import { X, MessageSquare } from "lucide-react";

export const TranscriptModal = ({
  isOpen,
  onClose,
  call,
  mode,
}) => {
  if (!isOpen || !call) return null;

  // Safe string converter
  const safeStr = (val) => {
    if (val === null || val === undefined) return "";
    if (typeof val === "string") return val;
    if (Array.isArray(val)) return val.map((v) => safeStr(v)).join(" ");
    if (typeof val === "object") return JSON.stringify(val);
    return String(val);
  };

  // Helper to parse forwarded transcripts into structured speaker turns
  const parseForwardedTranscript = (rawVal) => {
    const text = safeStr(rawVal);
    if (!text.trim()) return [];

    const lines = text.split("\n");
    const turns = [];

    let currentSpeaker = null;
    let currentText = "";

    // Matches speaker tags: "Speaker 1:", "Speaker 2:", etc.
    const speakerRegex =
      /^\s*(Speaker\s+\d+|Channel\s+\d+|User|Agent|Customer|Speaker)\s*:\s*(.*)$/i;

    for (let line of lines) {
      line = line.trim();
      if (!line) continue;

      const match = line.match(speakerRegex);
      if (match) {
        if (currentSpeaker && currentText) {
          turns.push({ speaker: currentSpeaker, text: currentText.trim() });
        }
        currentSpeaker = match[1].trim();
        currentText = match[2].trim();
      } else {
        if (currentSpeaker) {
          currentText += " " + line;
        } else {
          currentSpeaker = "Speaker 1";
          currentText = line;
        }
      }
    }

    if (currentSpeaker && currentText) {
      turns.push({ speaker: currentSpeaker, text: currentText.trim() });
    }

    // Fallback if no speakers were identified
    if (turns.length === 0 && text.trim()) {
      const paragraphs = text.split(/\n\n+/);
      paragraphs.forEach((p, index) => {
        if (p.trim()) {
          turns.push({
            speaker: index % 2 === 0 ? "Customer" : "Support Agent",
            text: p.trim(),
          });
        }
      });
    }

    return turns;
  };

  const renderContent = () => {
    if (mode === "standard") {
      const transcript = call.transcript || [];
      if (transcript.length === 0) {
        return (
          <div className="empty-state">
            <MessageSquare size={48} />
            <p>No conversation logs recorded for this call.</p>
          </div>
        );
      }

      return transcript.map((msg, index) => {
        const isUser = msg.role === "user";
        const containerClass = isUser ? "user" : "agent";
        const bubbleClass = isUser ? "user" : "agent";
        const label = isUser ? "User" : "AI Agent";
        const timestampStr = msg.timestamp ? ` • ${msg.timestamp}` : "";

        return (
          <div key={index} className={`chat-bubble-container ${containerClass}`}>
            <div className="bubble-meta">
              <span className="bubble-label">{label}</span>
              <span className="bubble-time">{timestampStr}</span>
            </div>
            <div className={`chat-bubble ${bubbleClass}`}>
              <div className="bubble-content">{msg.text}</div>
            </div>
          </div>
        );
      });
    } else {
      if (!call.call_forwarded) {
        return (
          <div className="empty-state">
            <MessageSquare size={48} />
            <p>No forwarded conversation transcript recorded.</p>
          </div>
        );
      }

      if (!call.forwarded_transcript) {
        return (
          <div className="empty-state">
            <MessageSquare size={48} />
            <p>Waiting for forwarded call recording transcription...</p>
          </div>
        );
      }

      const turns = parseForwardedTranscript(call.forwarded_transcript);
      return turns.map((turn, index) => {
        const isUser =
          turn.speaker.toLowerCase().includes("speaker 1") ||
          turn.speaker.toLowerCase().includes("channel 0") ||
          turn.speaker.toLowerCase().includes("customer") ||
          turn.speaker.toLowerCase().includes("user");

        const containerClass = isUser ? "user" : "agent";
        const bubbleClass = isUser ? "user" : "forwarded-agent";
        const label = isUser ? "Customer" : "Support Agent";

        return (
          <div
            key={index}
            className={`chat-bubble-container ${containerClass} ${
              !isUser ? "forwarded-agent-meta" : ""
            }`}
          >
            <div className="bubble-meta">
              <span className="bubble-label">{label}</span>
              <span className="bubble-speaker">({turn.speaker})</span>
            </div>
            <div className={`chat-bubble ${bubbleClass}`}>
              <div className="bubble-content" style={{ whiteSpace: "pre-wrap" }}>
                {turn.text}
              </div>
            </div>
          </div>
        );
      });
    }
  };

  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) {
      onClose();
    }
  };

  const title =
    mode === "standard"
      ? `Conversation: ${call.phone_number || "Unknown"}`
      : `Forwarded Call Transcript: ${call.phone_number || "Unknown"}`;

  return (
    <div
      className={`modal-overlay active`}
      onClick={handleOverlayClick}
      style={{ display: "flex" }}
    >
      <div className="modal-content">
        <div className="modal-header">
          <span className="modal-title">{title}</span>
          <button className="modal-close-btn" onClick={onClose}>
            <X size={18} />
          </button>
        </div>
        <div className="modal-body">{renderContent()}</div>
        <div className="modal-footer">
          <button
            className="btn btn-secondary"
            onClick={onClose}
            style={{ minWidth: "80px" }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
