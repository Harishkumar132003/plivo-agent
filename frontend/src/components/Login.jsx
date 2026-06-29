import React, { useState } from "react";
import {
  Lock,
  Mail,
  AlertCircle,
  Phone,
  BarChart2,
  Settings,
} from "lucide-react";
import { getApiUrl } from "../api";

export const Login = ({ onLoginSuccess }) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const response = await fetch(getApiUrl("/api/login"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(
          data.detail || "Invalid credentials. Please try again.",
        );
      }

      if (data.token) {
        onLoginSuccess(data.token, data.username);
      } else {
        throw new Error("Invalid response from server.");
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-wrapper animate-fade-in">
      {/* ── Left Panel ── */}
      <div className="login-left">
        <div className="login-left-content">
          <div className="login-brand-logo">
            <Phone size={28} strokeWidth={2} color="#fff" />
          </div>
          <h2>Goodwind Technologies</h2>
          <p>
            AI-powered voice support management for your customer operations.
          </p>

          <div className="login-feature-list">
            <div className="feature-item">
              <div className="feature-icon">
                <BarChart2 size={16} color="#fff" />
              </div>
              Real-time call analytics &amp; transcripts
            </div>
            <div className="feature-item">
              <div className="feature-icon">
                <Phone size={16} color="#fff" />
              </div>
              Outbound dialer &amp; call management
            </div>
            <div className="feature-item">
              <div className="feature-icon">
                <Settings size={16} color="#fff" />
              </div>
              Dynamic AI agent configuration
            </div>
          </div>
        </div>
      </div>

      {/* ── Right Panel (Form) ── */}
      <div className="login-right">
        <div className="login-form-wrap">
          <div className="login-form-header">
            <div className="login-form-icon">
              <Lock size={20} strokeWidth={2.5} />
            </div>
            <h1>Welcome back</h1>
            <p>Sign in to your dashboard to continue</p>
          </div>

          {error && (
            <div
              className="alert-banner alert-error animate-slide-down"
              style={{ marginBottom: "1.25rem" }}
            >
              <AlertCircle size={15} strokeWidth={2.5} />
              <span>{error}</span>
            </div>
          )}

          <form
            onSubmit={handleSubmit}
            style={{ display: "flex", flexDirection: "column", gap: "1.1rem" }}
          >
            <div className="form-group">
              <label className="form-label" htmlFor="login-username">
                Email / Username
              </label>
              <div className="input-with-icon">
                <Mail className="input-icon" size={15} />
                <input
                  type="text"
                  id="login-username"
                  className="form-control"
                  placeholder="Enter your email or username"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  required
                  disabled={loading}
                  autoComplete="username"
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label" htmlFor="login-password">
                Password
              </label>
              <div className="input-with-icon">
                <Lock className="input-icon" size={15} />
                <input
                  type="password"
                  id="login-password"
                  className="form-control"
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  disabled={loading}
                  autoComplete="current-password"
                />
              </div>
            </div>

            <button
              type="submit"
              className="btn-login"
              disabled={loading}
              style={{ marginTop: "0.25rem" }}
            >
              {loading ? (
                <>
                  <svg
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                    style={{ animation: "spin 1s linear infinite" }}
                  >
                    <path d="M21 12a9 9 0 1 1-6.219-8.56" />
                  </svg>
                  Authenticating…
                </>
              ) : (
                "Sign in to Dashboard"
              )}
            </button>
          </form>

          <div className="login-form-footer">
            Protected administrative interface &mdash; Goodwind Technologies
            &copy; 2026
          </div>
        </div>
      </div>
    </div>
  );
};
