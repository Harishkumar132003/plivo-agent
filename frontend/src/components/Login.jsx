import React, { useState } from "react";
import { Lock, User, AlertCircle } from "lucide-react";

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
      const response = await fetch("/api/login", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
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
    <div className="login-container">
      <div className="login-card animate-fade-in">
        <div className="login-header">
          <div className="logo-glow-wrapper">
            <div className="logo-ring">
              <Lock className="logo-icon" size={24} strokeWidth={2.5} />
            </div>
          </div>
          <h2>Goodwind Technologies</h2>
          {/* <p>AI Support Portal Login</p> */}
        </div>

        {error && (
          <div className="alert-banner alert-error animate-slide-down">
            <AlertCircle size={16} strokeWidth={2.5} />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label" htmlFor="login-username">
              Username
            </label>
            <div className="input-with-icon">
              <User className="input-icon" size={16} />
              <input
                type="text"
                id="login-username"
                className="form-control"
                placeholder="Enter username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                required
                disabled={loading}
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="login-password">
              Password
            </label>
            <div className="input-with-icon">
              <Lock className="input-icon" size={16} />
              <input
                type="password"
                id="login-password"
                className="form-control"
                placeholder="Enter password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                disabled={loading}
              />
            </div>
          </div>

          <button type="submit" className="btn btn-login" disabled={loading}>
            {loading ? "Authenticating..." : "Sign In to Dashboard"}
          </button>
        </form>

        {/* <div className="login-footer">
          <span>Protected Administrative Interface</span>
        </div> */}
      </div>
    </div>
  );
};
