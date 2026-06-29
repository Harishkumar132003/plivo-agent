import React, { useState, useEffect } from "react";
import { Save, Pencil, X, RotateCcw, Lock, Unlock } from "lucide-react";

export const SettingsForm = ({ initialSettings, onSave, onToast }) => {
  const [welcomeMessage, setWelcomeMessage] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [forwardToNumber, setForwardToNumber] = useState("");
  const [loading, setLoading] = useState(false);
  const [isEditing, setIsEditing] = useState(false);

  // Snapshot for cancel/discard
  const [snapshot, setSnapshot] = useState(null);

  const defaultSettings = {
    welcome_message:
      "Hello, thank you for calling Goodwind Technologies support. How can I help you today?",
    system_prompt: `You are a voice support agent for Goodwind Technologies handling inbound calls.

RULES:
- Phone call. Max 1-2 short sentences per response. No markdown, bullets, or emojis.
- Speak at a brisk, natural phone-call pace. Never speak slowly or add long pauses.
- Respond immediately after the caller finishes — do not hesitate or overthink.
- Always reply in whatever language the customer speaks (English, Tamil, or Malayalam). Detect it automatically. Never ask them to choose.
- Never fabricate order information. Only relay what check_order_status returns.
- LANGUAGE FLOW:
  * Automatic Switch: If you detect the customer speaking Tamil or Malayalam, call set_language immediately. Change language and converse in it. Do NOT re-mention or repeatedly talk about the language in subsequent turns.
  * Requested Switch: If the customer explicitly requests a language change (e.g. "please speak in Tamil" or "change to Malayalam"), call set_language, inform them once in the target language that you have switched (e.g. "Sure, switching to Tamil" or "ശരി, മലയാളത്തിൽ സംസാരിക്കാം"), and then continue in that language.
  * Malayalam vs Tamil: Clearly identify the difference between Malayalam and Tamil. They are distinct languages with different vocabularies and scripts. Never mix Tamil words/grammar/scripts into Malayalam, or Malayalam words/grammar/scripts into Tamil. Keep them strictly separate and accurate.

FLOW:

STEP 1 — GREET IMMEDIATELY: As soon as the call connects, YOU speak first. Greet the caller by saying exactly: "{welcome_message}". Never wait for the caller to speak first.

STEP 2 — After customer speaks, classify IMMEDIATELY and act:
  A. ORDER STATUS → ask for their 4-digit Order ID (once only), call check_order_status, relay result.
  B. ANYTHING ELSE (refunds, cancellations, returns, complaints, sales, speak to human) → say "I'll transfer you to a support agent now, please hold on." in their language, then call forward_call.
  C. UNCLEAR → one short clarifying question, then classify.

STEP 3 — ORDER RESULT:
  - Dispatched → say order is dispatched.
  - Quoted → say status is Quoted.
  - Error/not found → say unable to retrieve right now.
  Ask if anything else needed.

STEP 4 — CLOSE: Warm goodbye in their language, call end_conversation.

ORDER ID: 4 digits only. Words like "six one eight zero" = 6180. Do NOT read it back. Call check_order_status immediately.

FORWARD: Say "I'll transfer you to a support agent now, please hold on." first, then call forward_call immediately.

STRICT: Never answer refunds/cancellations/complaints/sales/returns. Always forward these.`,
    forward_to_number: "+918610467370",
  };

  useEffect(() => {
    if (initialSettings) {
      setWelcomeMessage(initialSettings.welcome_message || "");
      setSystemPrompt(initialSettings.system_prompt || "");
      setForwardToNumber(initialSettings.forward_to_number || "");
    }
  }, [initialSettings]);

  const handleEdit = () => {
    setSnapshot({ welcomeMessage, systemPrompt, forwardToNumber });
    setIsEditing(true);
  };

  const handleCancel = () => {
    if (snapshot) {
      setWelcomeMessage(snapshot.welcomeMessage);
      setSystemPrompt(snapshot.systemPrompt);
      setForwardToNumber(snapshot.forwardToNumber);
    }
    setIsEditing(false);
    setSnapshot(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();

    if (!systemPrompt.includes("{welcome_message}")) {
      onToast?.(
        "System prompt must contain the '{welcome_message}' placeholder.",
        "error",
      );
      return;
    }

    const e164Regex = /^\+[1-9]\d{1,14}$/;
    if (!e164Regex.test(forwardToNumber)) {
      onToast?.(
        "Enter a valid phone number in E.164 format (e.g. +918610467370).",
        "error",
      );
      return;
    }

    setLoading(true);
    const success = await onSave({
      welcome_message: welcomeMessage,
      system_prompt: systemPrompt,
      forward_to_number: forwardToNumber,
    });
    setLoading(false);

    if (success) {
      onToast?.("Agent configuration updated successfully!", "success");
      setIsEditing(false);
      setSnapshot(null);
    } else {
      onToast?.("Failed to update configuration. Please try again.", "error");
    }
  };

  const handleReset = () => {
    setWelcomeMessage(defaultSettings.welcome_message);
    setSystemPrompt(defaultSettings.system_prompt);
    setForwardToNumber(defaultSettings.forward_to_number);
    onToast?.(
      "Fields reset to defaults. Click 'Save Changes' to apply.",
      "success",
    );
  };

  return (
    <div className="settings-page">
      {/* ── Header Row ── */}
      <div className="settings-header-row">
        <div className="settings-title-group">
          <h2 className="settings-title">Agent Configuration</h2>
          <p className="settings-subtitle">
            Manage your AI voice agent's greeting, instructions, and call
            routing.
          </p>
        </div>

        <div className="settings-header-actions">
          {!isEditing ? (
            <button
              type="button"
              className="btn btn-edit-config"
              onClick={handleEdit}
            >
              <Pencil size={14} strokeWidth={2.5} />
              Edit Configuration
            </button>
          ) : (
            <div className="settings-edit-pill">
              <Unlock size={12} strokeWidth={2.5} />
              Editing
            </div>
          )}
        </div>
      </div>

      {/* ── Status Banner ── */}
      {!isEditing && (
        <div className="settings-locked-notice">
          <Lock size={13} strokeWidth={2.5} />
          <span>
            Fields are locked. Click <strong>Edit Configuration</strong> to make
            changes.
          </span>
        </div>
      )}

      {/* ── Form ── */}
      <form onSubmit={handleSubmit} className="settings-form">
        {/* Welcome Message */}
        <div className="settings-field-card">
          <div className="settings-field-header">
            <div>
              <label
                className="settings-field-label"
                htmlFor="welcome-message-input"
              >
                Welcome Message
              </label>
              <p className="settings-field-desc">
                The greeting spoken by the voice agent immediately upon call
                connection.
              </p>
            </div>
          </div>
          <input
            type="text"
            id="welcome-message-input"
            className={`form-control settings-input ${!isEditing ? "field-locked" : ""}`}
            placeholder="e.g. Hello, thank you for calling. How can I help you?"
            value={welcomeMessage}
            onChange={(e) => setWelcomeMessage(e.target.value)}
            disabled={!isEditing}
            required
          />
        </div>

        {/* System Prompt */}
        <div className="settings-field-card">
          <div className="settings-field-header">
            <div>
              <label
                className="settings-field-label"
                htmlFor="system-prompt-input"
              >
                Instructions Prompt
                <span className="settings-field-tag">System Instructions</span>
              </label>
              <p className="settings-field-desc">
                Defines rules, language behavior, and step-by-step logic the
                agent follows during the call.{" "}
                <span className="placeholder-hint">
                  Must include &#123;welcome_message&#125;
                </span>
              </p>
            </div>
          </div>
          <textarea
            id="system-prompt-input"
            className={`form-control settings-textarea ${!isEditing ? "field-locked" : ""}`}
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            disabled={!isEditing}
            required
          />
        </div>

        {/* Call Forwarding Number */}
        <div className="settings-field-card">
          <div className="settings-field-header">
            <div>
              <label
                className="settings-field-label"
                htmlFor="forward-number-input"
              >
                Call Forwarding Number
              </label>
              <p className="settings-field-desc">
                Destination number in E.164 format (e.g., +918610467370) for
                human agent transfers.
              </p>
            </div>
          </div>
          <input
            type="text"
            id="forward-number-input"
            className={`form-control settings-input ${!isEditing ? "field-locked" : ""}`}
            placeholder="+918610467370"
            value={forwardToNumber}
            onChange={(e) => setForwardToNumber(e.target.value)}
            disabled={!isEditing}
            required
          />
        </div>

        {/* ── Action Row (only in edit mode) ── */}
        {isEditing && (
          <div className="settings-action-row animate-fade-in">
            <button
              type="button"
              className="btn btn-ghost"
              onClick={handleReset}
              disabled={loading}
            >
              <RotateCcw size={14} strokeWidth={2.5} />
              Reset to Defaults
            </button>

            <div className="settings-action-right">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={handleCancel}
                disabled={loading}
              >
                <X size={14} strokeWidth={2.5} />
                Cancel
              </button>
              <button
                type="submit"
                className="btn btn-primary"
                disabled={loading}
              >
                <Save size={14} strokeWidth={2.5} />
                {loading ? "Saving…" : "Save Changes"}
              </button>
            </div>
          </div>
        )}
      </form>
    </div>
  );
};
