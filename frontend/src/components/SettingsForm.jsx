import React, { useState, useEffect } from "react";
import { Save, AlertCircle } from "lucide-react";

export const SettingsForm = ({
  initialSettings,
  onSave,
}) => {
  const [welcomeMessage, setWelcomeMessage] = useState("");
  const [systemPrompt, setSystemPrompt] = useState("");
  const [forwardToNumber, setForwardToNumber] = useState("");
  const [loading, setLoading] = useState(false);

  // Alert State
  const [alert, setAlert] = useState(null);

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

  // Populate local fields when initialSettings are loaded
  useEffect(() => {
    if (initialSettings) {
      setWelcomeMessage(initialSettings.welcome_message || "");
      setSystemPrompt(initialSettings.system_prompt || "");
      setForwardToNumber(initialSettings.forward_to_number || "");
    }
  }, [initialSettings]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setAlert(null);

    // Validate prompt placeholder
    if (!systemPrompt.includes("{welcome_message}")) {
      setAlert({
        message:
          "Validation Warning: The system prompt must contain the '{welcome_message}' placeholder so the greeting can be template-injected dynamically.",
        type: "error",
      });
      return;
    }

    // Validate phone number format (E.164)
    const e164Regex = /^\+[1-9]\d{1,14}$/;
    if (!e164Regex.test(forwardToNumber)) {
      setAlert({
        message:
          "Validation Warning: Please enter a valid phone number in E.164 format (e.g. +918610467370).",
        type: "error",
      });
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
      setAlert({
        message: "Configuration settings updated successfully and saved in DB!",
        type: "success",
      });
    } else {
      setAlert({
        message: "Failed to update configuration settings in the database.",
        type: "error",
      });
    }
  };

  const handleReset = () => {
    if (
      window.confirm(
        "Are you sure you want to reset settings to default values? Note: You will still need to click 'Save Configuration' to apply changes to the database."
      )
    ) {
      setWelcomeMessage(defaultSettings.welcome_message);
      setSystemPrompt(defaultSettings.system_prompt);
      setForwardToNumber(defaultSettings.forward_to_number);
      setAlert({
        message: "Form fields reset to default values. Click 'Save Configuration' to submit.",
        type: "success",
      });
    }
  };

  return (
    <div className="settings-card">
      <h2
        style={{
          fontFamily: "var(--font-outfit)",
          fontWeight: 600,
          fontSize: "1.5rem",
          color: "var(--text-primary)",
          borderBottom: "1px solid var(--border-color)",
          paddingBottom: "0.75rem",
        }}
      >
        Agent Configuration
      </h2>

      {alert && (
        <div className={`alert-banner alert-${alert.type}`}>
          <AlertCircle size={16} />
          <span>{alert.message}</span>
        </div>
      )}

      <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1.5rem" }}>
        <div className="form-group">
          <label className="form-label" htmlFor="welcome-message-input">
            Welcome Message
          </label>
          <span className="form-desc">
            The greeting spoken by the voice agent immediately upon call connection.
          </span>
          <input
            type="text"
            id="welcome-message-input"
            className="form-control"
            placeholder="e.g. Hello, thank you for calling Goodwind Technologies. How can I help you?"
            value={welcomeMessage}
            onChange={(e) => setWelcomeMessage(e.target.value)}
            required
          />
        </div>

        <div className="form-group">
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <label className="form-label" htmlFor="system-prompt-input">
              Instructions Prompt (System Instructions)
            </label>
            <span className="placeholder-hint">Must contain the {"{welcome_message}"} placeholder</span>
          </div>
          <span className="form-desc">
            Define the rules, language behavior, and step-by-step logic the agent follows during the call.
          </span>
          <textarea
            id="system-prompt-input"
            className="form-control"
            style={{
              minHeight: "350px",
              fontFamily: "monospace",
              fontSize: "0.85rem",
              lineHeight: 1.5,
              resize: "vertical",
            }}
            value={systemPrompt}
            onChange={(e) => setSystemPrompt(e.target.value)}
            required
          />
        </div>

        <div className="form-group">
          <label className="form-label" htmlFor="forward-number-input">
            Call Forwarding Number
          </label>
          <span className="form-desc">
            The destination phone number (E.164 format, e.g., +918610467370) used when transferring calls to a human agent.
          </span>
          <input
            type="text"
            id="forward-number-input"
            className="form-control"
            placeholder="+918610467370"
            value={forwardToNumber}
            onChange={(e) => setForwardToNumber(e.target.value)}
            required
          />
        </div>

        <div
          style={{
            display: "flex",
            justifyContent: "flex-end",
            gap: "1rem",
            marginTop: "1rem",
            borderTop: "1px solid var(--border-color)",
            paddingTop: "1.5rem",
          }}
        >
          <button
            type="button"
            className="btn btn-outline"
            style={{
              borderColor: "var(--text-secondary)",
              color: "var(--text-secondary)",
            }}
            onClick={handleReset}
          >
            Reset to Defaults
          </button>
          <button type="submit" className="btn" disabled={loading}>
            <Save size={14} strokeWidth={2.5} />
            {loading ? "Saving..." : "Save Configuration"}
          </button>
        </div>
      </form>
    </div>
  );
};
