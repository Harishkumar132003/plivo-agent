import React, { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { CheckCircle2, XCircle, X } from "lucide-react";

/**
 * Single Toast item — auto-dismisses after ~3.8s.
 */
export const ToastItem = ({ id, message, type, onDismiss }) => {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    const hideTimer = setTimeout(() => setVisible(false), 3800);
    const removeTimer = setTimeout(() => onDismiss(id), 4300);
    return () => {
      clearTimeout(hideTimer);
      clearTimeout(removeTimer);
    };
  }, [id, onDismiss]);

  return (
    <div className={`toast-item toast-${type} ${visible ? "toast-show" : "toast-hide"}`}>
      <div className="toast-icon">
        {type === "success" ? (
          <CheckCircle2 size={18} strokeWidth={2} />
        ) : (
          <XCircle size={18} strokeWidth={2} />
        )}
      </div>
      <span className="toast-message">{message}</span>
      <button
        className="toast-close"
        onClick={() => {
          setVisible(false);
          setTimeout(() => onDismiss(id), 350);
        }}
        aria-label="Dismiss"
      >
        <X size={14} strokeWidth={2.5} />
      </button>
    </div>
  );
};

/**
 * ToastContainer — uses a React Portal so it renders at document.body level,
 * completely outside any CSS stacking context (transform, filter, etc.).
 * This guarantees position:fixed works correctly across the entire viewport.
 */
export const ToastContainer = ({ toasts, onDismiss }) => {
  if (!toasts.length) return null;
  return createPortal(
    <div
      className="toast-container"
      role="region"
      aria-live="polite"
      aria-label="Notifications"
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} {...t} onDismiss={onDismiss} />
      ))}
    </div>,
    document.body
  );
};
