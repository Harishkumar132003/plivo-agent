import { useState, useEffect, useRef, useCallback } from "react";
import { RefreshCw, Settings, History, LogOut, Phone } from "lucide-react";
import { StatsCards } from "./components/StatsCards";
import { SearchBar } from "./components/SearchBar";
import { CallsTable } from "./components/CallsTable";
import { SettingsForm } from "./components/SettingsForm";
import { TranscriptModal } from "./components/TranscriptModal";
import { Login } from "./components/Login";
import { ToastContainer } from "./components/Toast";
import { getApiUrl } from "./api";
import "./App.scss";

function App() {
  const [calls, setCalls] = useState([]);
  const [settings, setSettings] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [debouncedSearchTerm, setDebouncedSearchTerm] = useState("");
  const [typeFilter, setTypeFilter] = useState("all");
  const [orderFilter, setOrderFilter] = useState("all");
  const [autoRefresh, setAutoRefresh] = useState(true);

  // Debounce search term to avoid spamming the API
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearchTerm(searchTerm);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm]);

  // ── Tab routing via URL hash ────────────────────────────────────────────
  const VALID_TABS = ["calls", "settings"];
  const getTabFromHash = () => {
    const hash = window.location.hash.replace("#", "");
    return VALID_TABS.includes(hash) ? hash : "calls";
  };
  const [activeTab, setActiveTab] = useState(getTabFromHash);

  // Keep tab in sync with the browser hash (back/forward navigation)
  useEffect(() => {
    const onHashChange = () => setActiveTab(getTabFromHash());
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  // When tab is changed programmatically, update the URL hash
  const navigateTab = (tab) => {
    window.location.hash = tab;
    setActiveTab(tab);
  };

  const [lastUpdated, setLastUpdated] = useState("Just now");
  const [refreshing, setRefreshing] = useState(false);

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

  // Toast State
  const [toasts, setToasts] = useState([]);
  const toastIdRef = useRef(0);

  const showToast = useCallback((message, type = "success") => {
    const id = ++toastIdRef.current;
    setToasts((prev) => [...prev, { id, message, type }]);
  }, []);

  const dismissToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  // Timer Ref
  const intervalRef = useRef(null);

  // Auth Header Helper
  const getAuthHeaders = () => ({ Authorization: `Bearer ${token}` });

  // Logout Handler
  const handleLogout = async () => {
    try {
      await fetch(getApiUrl("/api/logout"), { method: "POST", headers: getAuthHeaders() });
    } catch (e) {
      console.error("Logout request error:", e);
    }
    localStorage.removeItem("token");
    localStorage.removeItem("username");
    setToken("");
    setUsername("");
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

  // Fetch Calls
  const fetchCalls = useCallback(async () => {
    if (!token) return;

    setRefreshing(true);

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);

    try {
      const queryParams = new URLSearchParams();

      if (debouncedSearchTerm) {
        queryParams.append("search", debouncedSearchTerm);
      }

      if (typeFilter !== "all") {
        queryParams.append("type_filter", typeFilter);
      }

      if (orderFilter !== "all") {
        queryParams.append("order_filter", orderFilter);
      }

      const url = getApiUrl(`/api/calls?${queryParams.toString()}`);

      console.log("Type Filter:", typeFilter);
      console.log("Order Filter:", orderFilter);
      console.log("Request URL:", url);

      const response = await fetch(url, {
        headers: getAuthHeaders(),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (response.status === 401) {
        handleLogout();
        return;
      }

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const data = await response.json();

      console.log("Returned Calls:", data.length);

      setCalls(data);
      setLastUpdated(
        new Date().toLocaleTimeString([], {
          hour: "2-digit",
          minute: "2-digit",
        }),
      );
    } catch (err) {
      clearTimeout(timeoutId);
      if (err.name === "AbortError") {
        console.error("Fetch request timed out after 30 seconds");
        setLastUpdated("Sync timed out");
      } else {
        console.error(err);
        setLastUpdated("Failed to sync");
      }
    } finally {
      setTimeout(() => setRefreshing(false), 500);
    }
  }, [token, debouncedSearchTerm, typeFilter, orderFilter]);

  // Fetch Settings
  const fetchSettings = async () => {
    if (!token) return;
    try {
      const response = await fetch(getApiUrl("/api/settings"), {
        headers: getAuthHeaders(),
      });
      if (response.status === 401) {
        handleLogout();
        return;
      }
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      setSettings(data);
    } catch (error) {
      console.error("Error fetching settings:", error);
    }
  };

  // Save Settings
  const handleSaveSettings = async (newSettings) => {
    if (!token) return false;
    try {
      const response = await fetch(getApiUrl("/api/settings"), {
        method: "POST",
        headers: { "Content-Type": "application/json", ...getAuthHeaders() },
        body: JSON.stringify(newSettings),
      });
      if (response.status === 401) {
        handleLogout();
        return false;
      }
      if (!response.ok) throw new Error("Failed to save settings");
      setSettings(newSettings);
      return true;
    } catch (error) {
      console.error("Error saving settings:", error);
      return false;
    }
  };

  // Verify token & fetch data on mount/token change
  useEffect(() => {
    const verifyAndFetch = async () => {
      if (token) {
        setIsVerifying(true);
        try {
          const response = await fetch(getApiUrl("/api/verify-token"), {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (response.status === 401) {
            handleLogout();
            setIsVerifying(false);
            return;
          }
          if (!response.ok) throw new Error("Token validation failed");
          if (window.location.pathname !== "/dashboard") {
            window.history.pushState({}, "", "/dashboard");
          }
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
  }, [token, fetchCalls]);

  // Auto-refresh interval
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
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [autoRefresh, token, fetchCalls]);

  const handleOpenTranscript = (call, mode) => {
    setSelectedCall(call);
    setModalMode(mode);
  };

  // ── Verifying screen ──────────────────────────────────────────────────────
  if (isVerifying) {
    return (
      <div className="verifying-screen animate-fade-in">
        <div className="verifying-icon">
          <RefreshCw className="animate-spin" size={24} strokeWidth={2} />
        </div>
        <h2>Verifying Session</h2>
        <p>Please wait while we secure your dashboard…</p>
      </div>
    );
  }

  // ── Login screen ──────────────────────────────────────────────────────────
  if (!token) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  // ── Dashboard ─────────────────────────────────────────────────────────────
  const userInitials = username ? username.slice(0, 2).toUpperCase() : "U";

  return (
    <div className="dashboard-wrapper animate-fade-in">
      {/* ── Header ── */}
      <header className="dashboard-header">
        <div className="dashboard-header-inner">
          <div className="brand-section">
            <div className="brand-logo">
              <Phone size={18} strokeWidth={2.5} />
            </div>
            <div>
              <h1>Goodwind Technologies</h1>
              <div className="brand-sub">AI Voice Support Dashboard</div>
            </div>
          </div>

          <div className="header-controls">
            <div className="live-pill">
              <span className="live-dot" />
              Live
            </div>

            <div className="toggle-wrap">
              <span>Auto-Refresh</span>
              <label className="switch">
                <input
                  type="checkbox"
                  checked={autoRefresh}
                  onChange={(e) => setAutoRefresh(e.target.checked)}
                />
                <span className="slider" />
              </label>
            </div>

            <button
              className="btn btn-ghost"
              style={{ padding: "0.45rem 0.875rem" }}
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

            <div className="user-chip">
              <div className="user-avatar">{userInitials}</div>
              <span className="user-name">{username}</span>
            </div>

            <button
              className="btn btn-danger"
              style={{ padding: "0.45rem 0.875rem" }}
              onClick={handleLogout}
            >
              <LogOut size={14} strokeWidth={2.5} />
              Sign Out
            </button>
          </div>
        </div>
      </header>

      {/* ── Page Content ── */}
      <div className="dashboard-container">
        <div className="page-content">
          {/* Stats */}
          <StatsCards calls={calls} />

          {/* Tabs */}
          <div className="tabs-container">
            <button
              className={`tab-btn ${activeTab === "calls" ? "active" : ""}`}
              onClick={() => navigateTab("calls")}
            >
              <History size={15} strokeWidth={2.5} />
              Call History
            </button>
            <button
              className={`tab-btn ${activeTab === "settings" ? "active" : ""}`}
              onClick={() => navigateTab("settings")}
            >
              <Settings size={15} strokeWidth={2.5} />
              Agent Configuration
            </button>
          </div>

          {/* Tab Panels */}
          {activeTab === "calls" ? (
            <div id="call-history-section">
              <div className="search-filter-row">
                <SearchBar value={searchTerm} onChange={setSearchTerm} />
              </div>
              <CallsTable
                calls={calls}
                lastUpdated={lastUpdated}
                onOpenTranscript={handleOpenTranscript}
                typeFilter={typeFilter}
                setTypeFilter={setTypeFilter}
                orderFilter={orderFilter}
                setOrderFilter={setOrderFilter}
              />
            </div>
          ) : (
            <div id="settings-section">
              <SettingsForm
                initialSettings={settings}
                onSave={handleSaveSettings}
                onToast={showToast}
              />
            </div>
          )}
        </div>
      </div>

      {/* Transcript Modal */}
      <TranscriptModal
        isOpen={selectedCall !== null}
        onClose={() => setSelectedCall(null)}
        call={selectedCall}
        mode={modalMode}
      />

      {/* Toast Notifications */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </div>
  );
}

export default App;
