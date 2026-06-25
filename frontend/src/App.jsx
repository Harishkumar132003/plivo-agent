import { useState, useEffect, useRef } from "react";
import { RefreshCw, Settings, History } from "lucide-react";
import { StatsCards } from "./components/StatsCards";
import { SearchBar } from "./components/SearchBar";
import { CallsTable } from "./components/CallsTable";
import { SettingsForm } from "./components/SettingsForm";
import { TranscriptModal } from "./components/TranscriptModal";
import "./App.scss";

function App() {
  const [calls, setCalls] = useState([]);
  const [settings, setSettings] = useState(null);
  const [searchTerm, setSearchTerm] = useState("");
  const [activeTab, setActiveTab] = useState("calls");
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [lastUpdated, setLastUpdated] = useState("Last updated: Just now");
  const [refreshing, setRefreshing] = useState(false);

  // Modal State
  const [selectedCall, setSelectedCall] = useState(null);
  const [modalMode, setModalMode] = useState("standard");

  // Timer Ref
  const intervalRef = useRef(null);

  // Fetch Calls from FastAPI
  const fetchCalls = async () => {
    setRefreshing(true);
    try {
      const response = await fetch("/api/calls");
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
    try {
      const response = await fetch("/api/settings");
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
    try {
      const response = await fetch("/api/settings", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(newSettings),
      });

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

  // Set up auto refresh interval
  useEffect(() => {
    fetchCalls();
    fetchSettings();
  }, []);

  useEffect(() => {
    if (autoRefresh) {
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
  }, [autoRefresh]);

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

  return (
    <div className="container">
      <header>
        <div className="brand-section">
          <h1>Goodwind Technologies</h1>
          <p>AI Voice Support Call Logs</p>
        </div>
        <div className="controls">
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
          <button className="btn" onClick={fetchCalls} disabled={refreshing}>
            <RefreshCw
              size={14}
              strokeWidth={2.5}
              className={refreshing ? "refreshing-icon" : ""}
            />
            Refresh
          </button>
        </div>
      </header>

      {/* Statistics Cards */}
      <StatsCards
        calls={calls}
        hotlineNumber={settings?.forward_to_number || "+91 80 3133 9945"}
      />

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
          <SearchBar value={searchTerm} onChange={setSearchTerm} />
          <CallsTable
            calls={filteredCalls}
            lastUpdated={lastUpdated}
            onOpenTranscript={handleOpenTranscript}
          />
        </div>
      ) : (
        <div id="settings-section">
          <SettingsForm initialSettings={settings} onSave={handleSaveSettings} />
        </div>
      )}

      {/* Transcript Overlay modal */}
      <TranscriptModal
        isOpen={selectedCall !== null}
        onClose={() => setSelectedCall(null)}
        call={selectedCall}
        mode={modalMode}
      />
    </div>
  );
}

export default App;
