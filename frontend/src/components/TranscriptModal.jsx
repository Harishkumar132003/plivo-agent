import React, { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import { X, MessageSquare, Bot, User, PhoneCall, Phone } from "lucide-react";

export const TranscriptModal = ({
  isOpen,
  onClose,
  call,
  mode = "standard",
}) => {
  const [modalTab, setModalTab] = useState("standard");
  const modalBodyRef = useRef(null);

  // Sync tab when mode or call changes
  useEffect(() => {
    if (call) setModalTab(mode);
  }, [call, mode]);

  // Lock body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "";
    }
    return () => { document.body.style.overflow = ""; };
  }, [isOpen]);

  // Auto-scroll to bottom on open or tab change
  useEffect(() => {
    if (isOpen && modalBodyRef.current) {
      const timer = setTimeout(() => {
        if (modalBodyRef.current) {
          modalBodyRef.current.scrollTop = modalBodyRef.current.scrollHeight;
        }
      }, 120);
      return () => clearTimeout(timer);
    }
  }, [isOpen, modalTab, call]);

  if (!isOpen || !call) return null;

  // ── Helpers ──────────────────────────────────────────────────────────────
  const safeStr = (val) => {
    if (val === null || val === undefined) return "";
    if (typeof val === "string") return val;
    if (Array.isArray(val)) return val.map((v) => safeStr(v)).join(" ");
    if (typeof val === "object") return JSON.stringify(val);
    return String(val);
  };

  const parseForwardedTranscript = (rawVal) => {
    const text = safeStr(rawVal);
    if (!text.trim()) return [];

    const lines = text.split("\n");
    const turns = [];
    let currentSpeaker = null;
    let currentText = "";

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

  // ── Content Renderer ─────────────────────────────────────────────────────
  const renderContent = () => {
    if (modalTab === "standard") {
      const transcript = call.transcript || [];
      if (transcript.length === 0) {
        return (
          <div className="empty-state">
            <MessageSquare size={40} />
            <p>No conversation logs recorded for this call.</p>
          </div>
        );
      }

      return transcript.map((msg, index) => {
        const isUser = msg.role === "user";
        const label = isUser ? "User" : "AI Agent";
        const timestampStr = msg.timestamp ? ` • ${msg.timestamp}` : "";

        return (
          <div
            key={index}
            className={`chat-bubble-container ${isUser ? "user" : "agent"}`}
            style={{ animationDelay: `${index * 0.04}s` }}
          >
            <div className="bubble-meta">
              <span className="bubble-label" style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
                {isUser ? <User size={11} /> : <Bot size={11} />}
                {label}
              </span>
              <span className="bubble-time">{timestampStr}</span>
            </div>
            <div className={`chat-bubble ${isUser ? "user" : "agent"}`}>
              {msg.text}
            </div>
          </div>
        );
      });
    }

    // ── Forwarded tab ───────────────────────────────────────────────────
    if (!call.call_forwarded) {
      return (
        <div className="empty-state">
          <MessageSquare size={40} />
          <p>No forwarded conversation transcript recorded.</p>
        </div>
      );
    }

    if (!call.forwarded_transcript) {
      return (
        <div className="empty-state">
          <PhoneCall size={40} style={{ color: "var(--warning-text)" }} />
          <p style={{ marginTop: "0.75rem" }}>
            Waiting for forwarded call recording transcription…
          </p>
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

      return (
        <div
          key={index}
          className={`chat-bubble-container ${isUser ? "user" : "agent"}`}
          style={{ animationDelay: `${index * 0.04}s` }}
        >
          <div className="bubble-meta">
            <span className="bubble-label" style={{ display: "flex", alignItems: "center", gap: "0.25rem" }}>
              {isUser ? <User size={11} /> : <Phone size={11} />}
              {isUser ? "Customer" : "Support Agent"}
            </span>
            <span className="bubble-time">({turn.speaker})</span>
          </div>
          <div className={`chat-bubble ${isUser ? "user" : "forwarded-agent"}`}>
            <div style={{ whiteSpace: "pre-wrap" }}>{turn.text}</div>
          </div>
        </div>
      );
    });
  };

  // ── Overlay click to close ────────────────────────────────────────────
  const handleOverlayClick = (e) => {
    if (e.target === e.currentTarget) onClose();
  };

  // ── Render via portal so it always sits on top of everything ─────────
  return createPortal(
    <div className="modal-overlay active" onClick={handleOverlayClick}>
      <div className="modal-content" role="dialog" aria-modal="true">
        {/* Header */}
        <div className="modal-header">
          <span className="modal-title">
            Call: {call.phone_number || "Unknown"}
          </span>
          <button className="modal-close-btn" onClick={onClose} aria-label="Close">
            <X size={16} />
          </button>
        </div>

        {/* Tabs — only shown for forwarded calls */}
        {call.call_forwarded && (
          <div className="modal-tabs">
            <button
              className={`modal-tab-btn ${modalTab === "standard" ? "active" : ""}`}
              onClick={() => setModalTab("standard")}
            >
              AI Agent Conversation
            </button>
            <button
              className={`modal-tab-btn ${modalTab === "forwarded" ? "active" : ""}`}
              onClick={() => setModalTab("forwarded")}
            >
              Support Agent (Forwarded)
            </button>
          </div>
        )}

        {/* Body */}
        <div className="modal-body" ref={modalBodyRef}>
          {renderContent()}
        </div>

        {/* Footer */}
        <div className="modal-footer">
          <button className="btn btn-ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
};
