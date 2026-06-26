import { useState, useEffect, useRef } from "react";
import { RefreshCw, Settings, History, LogOut, Sun, Moon } from "lucide-react";
import { StatsCards } from "./components/StatsCards";
import { AnalyticsSection } from "./components/AnalyticsSection";
import { SearchBar } from "./components/SearchBar";
import { CallsTable } from "./components/CallsTable";
import { SettingsForm } from "./components/SettingsForm";
import { TranscriptModal } from "./components/TranscriptModal";
import { Login } from "./components/Login";
import "./App.scss";

function App() {
  const [calls, setCalls] = useState([]);
  const [settings, setSettings] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [activeTab, setActiveTab] = useState("calls");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdated, setLastUpdated] = useState("Last updated: Just now");
  const [refreshing, setRefreshing] = useState(false);

  // Theme & Callback State
  const [theme, setTheme] = useState(localStorage.getItem("theme") || "light");
  const [callbackNumber, setCallbackNumber] = useState("");

  // Authentication State
  const [token, setToken] = useState(localStorage.getItem("token") || "");
  const [username, setUsername] = useState(
    localStorage.getItem("username") || "",
  );
  const [isVerifying, setIsVerifying] = useState(
    !!localStorage.getItem("token"),
  );

  // Modal State
  const [selectedCall, setSelectedCall] = useState(null);
  const [modalMode, setModalMode] = useState("standard");

  // Timer Ref
  const intervalRef = useRef(null);

  // Apply Theme on change
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("theme", theme);
  }, [theme]);

  const toggleTheme = () => {
    setTheme((prev) => (prev === "light" ? "dark" : "light"));
  };

  // Auth Header Helper
  const getAuthHeaders = () => {
    return {
      Authorization: `Bearer ${token}`,
    };
  };

  // Logout Handler
  const handleLogout = async () => {
    try {
      await fetch("/api/logout", {
        method: "POST",
        headers: getAuthHeaders(),
      });
    } catch (e) {
      console.error("Logout request error:", e);
    }
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    setToken("");
    setUsername("");
    if (window.location.pathname !== "/dashboard") {
      window.history.pushState({}, "", "/dashboard");
    }
  };

  // Login Success Handler
  const handleLoginSuccess = (newToken, newUsername) => {
    localStorage.setItem("token", newToken);
    localStorage.setItem("username", newUsername);
    setToken(newToken);
    setUsername(newUsername);
    if (window.location.pathname !== "/dashboard") {
      window.history.pushState({}, "", "/dashboard");
    }
  };

  // Fetch Calls from FastAPI
  const fetchCalls = async () => {
    if (!token) return;
    setRefreshing(true);
    try {
      const response = await fetch("/api/calls", {
        headers: getAuthHeaders(),
      });

      if (response.status === 401) {
        handleLogout();
        return;
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      setCalls(data);
      setLastUpdated(`Last updated: ${new Date().toLocaleTimeString()}`);
    } catch (error) {
      console.error("Error fetching call logs:", error);
      setLastUpdated("Last updated: Failed to sync");
    } finally {
      setTimeout(() => setRefreshing(false), 500);
    }
  };

  // Fetch Settings from FastAPI
  const fetchSettings = async () => {
    if (!token) return;
    try {
      const response = await fetch("/api/settings", {
        headers: getAuthHeaders(),
      });

      if (response.status === 401) {
        handleLogout();
        return;
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();
      setSettings(data);
    } catch (error) {
      console.error("Error fetching settings:", error);
    }
  };

  // Save Settings via API
  const handleSaveSettings = async (newSettings) => {
    if (!token) return false;
    try {
      const response = await fetch("/api/settings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify(newSettings),
      });

      if (response.status === 401) {
        handleLogout();
        return false;
      }

      if (!response.ok) {
        throw new Error("Failed to save settings");
      }

      setSettings(newSettings);
      return true;
    } catch (error) {
      console.error("Error saving settings:", error);
      return false;
    }
  };

  // Initiate an outbound call from the dashboard dialer
  const handleOutboundCall = async (customerNumber) => {
    try {
      const response = await fetch("/api/outbound-call", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...getAuthHeaders(),
        },
        body: JSON.stringify({ customer_number: customerNumber }),
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.detail || "Outbound call failed");
      }

      return await response.json();
    } catch (e) {
      console.error("Outbound call execution error:", e);
      throw e;
    }
  };

  // Populate dialer input and scroll to dialer stats card
  const handleInitiateCallback = (phoneNum) => {
    setCallbackNumber(phoneNum);
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  // Set up data fetching and token verification on mount/token change
  useEffect(() => {
    const verifyAndFetch = async () => {
      if (token) {
        setIsVerifying(true);
        try {
          const response = await fetch("/api/verify-token", {
            headers: {
              Authorization: `Bearer ${token}`,
            },
          });
          if (response.status === 401) {
            handleLogout();
            setIsVerifying(false);
            return;
          }
          if (!response.ok) {
            throw new Error("Token validation failed");
          }

          // Ensure URL is /dashboard if authenticated
          if (window.location.pathname !== "/dashboard") {
            window.history.pushState({}, "", "/dashboard");
          }

          // Fetch calls and settings
          await Promise.all([fetchCalls(), fetchSettings()]);
        } catch (error) {
          console.error("Token verification error:", error);
          handleLogout();
        } finally {
          setIsVerifying(false);
        }
      } else {
        setIsVerifying(false);
      }
    };
    verifyAndFetch();
  }, [token]);

  // Set up auto refresh interval
  useEffect(() => {
    if (autoRefresh && token) {
      intervalRef.current = window.setInterval(fetchCalls, 15000);
    } else {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
      }
    };
  }, [autoRefresh, token]);

  // Filter call logs by search term
  const filteredCalls = calls.filter((call) => {
    const term = searchTerm.toLowerCase().trim();
    if (!term) return true;

    const phone = (call.phone_number || "").toLowerCase();
    const order = (call.order_number || "").toLowerCase();
    const transcriptText = (call.transcript || [])
      .map((t) => t.text)
      .join(" ")
      .toLowerCase();
    const forwardedText = (call.forwarded_transcript || "").toLowerCase();

    return (
      phone.includes(term) ||
      order.includes(term) ||
      transcriptText.includes(term) ||
      forwardedText.includes(term)
    );
  });

  const handleOpenTranscript = (call, mode) => {
    setSelectedCall(call);
    setModalMode(mode);
  };

  // Render loading state if verifying session
  if (isVerifying) {
    return (
      <div className="login-container">
        <div
          className="login-card animate-fade-in"
          style={{ textAlign: "center", padding: "3rem" }}
        >
          <div className="logo-glow-wrapper">
            <div className="logo-ring">
              <RefreshCw
                className="logo-icon animate-spin"
                size={24}
                strokeWidth={2.5}
              />
            </div>
          </div>
          <h2 style={{ marginTop: "1.5rem" }}>Verifying Session...</h2>
          <p
            style={{
              color: "var(--text-secondary)",
              fontSize: "0.875rem",
              marginTop: "0.5rem",
            }}
          >
            Please wait while we secure your dashboard
          </p>
        </div>
      </div>
    );
  }

  // Render Login page if not authenticated
  if (!token) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <>
      <div className="container animate-fade-in">
        <header>
          <div className="brand-section">
            <h1>Goodwind Technologies</h1>
            <p>AI Voice Support Call Logs</p>
          </div>
          <div className="controls">
            <div className="user-welcome">
              <span>
                Welcome, <strong>{username}</strong>
              </span>
            </div>
            <div className="live-indicator">
              <span className="live-dot"></span>
              <span>Live</span>
            </div>
            <div className="toggle-container">
              <span>Auto-Refresh</span>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
                <span className="slider"></span>
              </label>
            </div>
            <button
              className="btn btn-outline"
              onClick={fetchCalls}
              disabled={refreshing}
            >
              <RefreshCw
                size={14}
                strokeWidth={2.5}
                className={refreshing ? "refreshing-icon" : ""}
              />
              Refresh
            </button>
            <button
              className="theme-toggle-btn"
              onClick={toggleTheme}
              title={`Toggle ${theme === "light" ? "Dark" : "Light"} Mode`}
              type="button"
            >
              {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
            </button>
            <button className="btn btn-logout" onClick={handleLogout}>
              <LogOut size={14} strokeWidth={2.5} />
              Sign Out
            </button>
          </div>
        </header>

        {/* Statistics Cards */}
        <StatsCards
          calls={calls}
          hotlineNumber={settings?.forward_to_number || "+91 80 3133 9945"}
          onDial={handleOutboundCall}
          callbackNumber={callbackNumber}
        />

        {/* Analytics SVG Charts */}
        {/* <AnalyticsSection calls={calls} /> */}

        {/* Tabs Navigation */}
        <div className="tabs-container">
          <button
            className={`tab-btn ${activeTab === "calls" ? "active" : ""}`}
            onClick={() => setActiveTab("calls")}
          >
            <History size={16} strokeWidth={2.5} />
            Call History
          </button>
          <button
            className={`tab-btn ${activeTab === "settings" ? "active" : ""}`}
            onClick={() => setActiveTab("settings")}
          >
            <Settings size={16} strokeWidth={2.5} />
            Agent Configuration
          </button>
        </div>

        {/* Active Tab Panel */}
        {activeTab === "calls" ? (
          <div id="call-history-section">
            <div className="search-filter-row">
              <SearchBar value={searchTerm} onChange={setSearchTerm} />
            </div>
            <CallsTable
              calls={filteredCalls}
              lastUpdated={lastUpdated}
              onOpenTranscript={handleOpenTranscript}
              onInitiateCallback={handleInitiateCallback}
            />
          </div>
        ) : (
          <div id="settings-section">
            <SettingsForm
              initialSettings={settings}
              onSave={handleSaveSettings}
            />
          </div>
        )}
      </div>
      {/* Transcript Overlay modal */}
      <TranscriptModal
        isOpen={selectedCall !== null}
        onClose={() => setSelectedCall(null)}
        call={selectedCall}
        mode={modalMode}
      />
    </>
  );
}

export default App;
