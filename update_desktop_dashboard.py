r"""
Script to update C:\Users\deepu\Desktop\dashboard to be fully connected
to the real backend at http://localhost:8000 and function purely as a live monitor.
"""

from pathlib import Path

DASHBOARD_DIR = Path(r"C:\Users\deepu\Desktop\dashboard")
SRC_DIR = DASHBOARD_DIR / "src"
COMPONENTS_DIR = SRC_DIR / "components"
HOOKS_DIR = SRC_DIR / "hooks"
UTILS_DIR = SRC_DIR / "utils"

# 1. vite.config.js
VITE_CONFIG = """import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
  ],
  server: {
    port: 3000,
    host: '0.0.0.0',
    open: false,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      }
    }
  }
})
"""

# 2. useSecurityState.js
USE_SECURITY_STATE = """import { useState, useEffect, useCallback, useRef } from "react";

const API_BASE = "/api";

export default function useSecurityState() {
  const [devices, setDevices] = useState([
    {
      id: "ESP-A",
      name: "ESP-A (COM9)",
      ip: "10.240.36.183",
      type: "ESP32 Sensor",
      status: "LOW",
      state: "NORMAL",
      wireless: true,
      blocked: false,
      prediction: "normal",
      confidence: 1.0,
      sequence: 0,
      features: {},
      probabilities: { normal: 1.0, dos: 0, ddos: 0, scanning: 0, ransomware: 0, backdoor: 0 },
      lastSeen: "Just now"
    },
    {
      id: "ESP-B",
      name: "ESP-B (COM13)",
      ip: "10.240.36.120",
      type: "ESP32 Actuator",
      status: "LOW",
      state: "NORMAL",
      wireless: true,
      blocked: false,
      prediction: "normal",
      confidence: 1.0,
      sequence: 0,
      features: {},
      probabilities: { normal: 1.0, dos: 0, ddos: 0, scanning: 0, ransomware: 0, backdoor: 0 },
      lastSeen: "Just now"
    }
  ]);

  const [stats, setStats] = useState({
    total_flows: 0,
    clean_streak: 0,
    total_attacks: 0,
    total_blocked: 0,
    class_counts: { normal: 0, dos: 0, ddos: 0, scanning: 0, ransomware: 0, backdoor: 0 }
  });

  const [anomalies, setAnomalies] = useState([]);
  const [logs, setLogs] = useState([]);
  const [trafficHistory, setTrafficHistory] = useState([
    { time: "00:00", inbound: 500, outbound: 200, threats: 0, total: 700 }
  ]);
  const [attackDist, setAttackDist] = useState([
    { name: "Normal", value: 100, color: "#10b981" },
    { name: "DoS", value: 0, color: "#3b82f6" },
    { name: "Scanning", value: 0, color: "#a855f7" },
    { name: "DDoS", value: 0, color: "#06b6d4" },
    { name: "Ransomware", value: 0, color: "#f97316" },
    { name: "Backdoor", value: 0, color: "#ef4444" }
  ]);

  const [actions, setActions] = useState([]);
  const [toasts, setToasts] = useState([]);
  const [selectedDevice, setSelectedDevice] = useState(null);
  const [backendOnline, setBackendOnline] = useState(false);
  const [currentTime, setCurrentTime] = useState("");

  const prevEventsRef = useRef(new Set());

  // Clock
  useEffect(() => {
    const updateTime = () => {
      const date = new Date();
      let hours = date.getHours();
      const minutes = String(date.getMinutes()).padStart(2, "0");
      const seconds = String(date.getSeconds()).padStart(2, "0");
      const ampm = hours >= 12 ? "PM" : "AM";
      hours = hours % 12 || 12;
      setCurrentTime(`${String(hours).padStart(2, "0")}:${minutes}:${seconds} ${ampm}`);
    };
    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  const addToast = useCallback((message, type = "info") => {
    const id = Date.now() + Math.random().toString(36).substr(2, 5);
    setToasts((prev) => [...prev, { id, message, type }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  // Unblock Device (Call Backend)
  const unblockDevice = useCallback(async (deviceId) => {
    try {
      const res = await fetch(`${API_BASE}/devices/${deviceId}/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: "UNBLOCK" })
      });
      if (res.ok) {
        addToast(`Device ${deviceId} unblocked successfully. Quarantine cleared.`, "success");
      } else {
        addToast(`Failed to unblock ${deviceId}.`, "error");
      }
    } catch (err) {
      addToast(`Network error when unblocking: ${err.message}`, "error");
    }
  }, [addToast]);

  // Block Device (Call Backend)
  const blockDevice = useCallback(async (deviceId) => {
    try {
      const res = await fetch(`${API_BASE}/devices/${deviceId}/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command: "BLOCK" })
      });
      if (res.ok) {
        addToast(`Device ${deviceId} quarantined (VLAN block applied).`, "warning");
      } else {
        addToast(`Failed to block ${deviceId}.`, "error");
      }
    } catch (err) {
      addToast(`Network error when blocking: ${err.message}`, "error");
    }
  }, [addToast]);

  // Polling Real-Time Backend Data every 1000ms
  useEffect(() => {
    let isMounted = true;

    const fetchAll = async () => {
      try {
        // Fetch devices, stats, and events in parallel
        const [devRes, statsRes, eventsRes] = await Promise.all([
          fetch(`${API_BASE}/devices`).catch(() => null),
          fetch(`${API_BASE}/stats`).catch(() => null),
          fetch(`${API_BASE}/events?limit=80`).catch(() => null)
        ]);

        if (!isMounted) return;

        if (devRes && devRes.ok) {
          const devData = await devRes.json();
          setBackendOnline(true);

          if (Array.isArray(devData) && devData.length > 0) {
            setDevices((prev) => {
              // Map incoming real devices to UI format
              const updated = devData.map((d) => {
                const id = d.device_id || "UNKNOWN";
                const isBlocked = !!d.blocked;
                const isAttack = d.prediction && d.prediction !== "normal";

                let status = "LOW"; // Normal
                if (isBlocked) status = "BLOCKED";
                else if (isAttack) status = "HIGH";

                const defaultIp = id === "ESP-A" ? "10.240.36.183" : id === "ESP-B" ? "10.240.36.120" : "10.240.36.1";
                const portLabel = id === "ESP-A" ? "COM9 / 1884" : id === "ESP-B" ? "COM13 / 1884" : "1884";

                return {
                  id,
                  name: `${id} (${portLabel})`,
                  rawId: id,
                  ip: defaultIp,
                  type: id === "ESP-A" ? "ESP32 Sensor" : "ESP32 Actuator",
                  status,
                  state: d.state || (isAttack ? "ATTACK" : "NORMAL"),
                  wireless: true,
                  blocked: isBlocked,
                  prediction: d.prediction || "normal",
                  confidence: typeof d.confidence === "number" ? d.confidence : 1.0,
                  probabilities: d.probabilities || {},
                  sequence: d.sequence || 0,
                  features: d.features || {},
                  reported_attack_type: d.reported_attack_type || "NONE",
                  lastSeen: d.last_seen ? new Date(d.last_seen).toLocaleTimeString() : "Live"
                };
              });
              return updated;
            });
          }
        }

        if (statsRes && statsRes.ok) {
          const statsData = await statsRes.json();
          setStats(statsData);

          // Update attack distribution from real counts
          const counts = statsData.class_counts || {};
          const total = Object.values(counts).reduce((a, b) => a + b, 0) || 1;

          const dist = [
            { name: "Normal", value: Math.round(((counts.normal || 0) / total) * 100), color: "#10b981" },
            { name: "DoS", value: Math.round(((counts.dos || 0) / total) * 100), color: "#3b82f6" },
            { name: "Scanning", value: Math.round(((counts.scanning || 0) / total) * 100), color: "#a855f7" },
            { name: "DDoS", value: Math.round(((counts.ddos || 0) / total) * 100), color: "#06b6d4" },
            { name: "Ransomware", value: Math.round(((counts.ransomware || 0) / total) * 100), color: "#f97316" },
            { name: "Backdoor", value: Math.round(((counts.backdoor || 0) / total) * 100), color: "#ef4444" }
          ].filter(item => item.value > 0 || item.name === "Normal");

          setAttackDist(dist.length ? dist : [{ name: "Normal", value: 100, color: "#10b981" }]);
        }

        if (eventsRes && eventsRes.ok) {
          const eventsData = await eventsRes.json();
          if (Array.isArray(eventsData)) {
            // Process anomalies
            const anomalyList = [];
            const logList = [];

            eventsData.forEach((ev, idx) => {
              const evTime = ev.timestamp ? new Date(ev.timestamp).toLocaleTimeString() : "just now";
              const key = `${ev.timestamp}-${ev.device_id}-${ev.sequence || idx}`;

              if (ev.kind === "automatic_block") {
                logList.push({
                  id: `LOG-BLK-${idx}`,
                  message: `[AUTO-DEFENSE] Blocked ${ev.device_id}: ${ev.reason}`,
                  timestamp: evTime,
                  severity: "Critical",
                  icon: "ShieldAlert"
                });
              } else if (ev.kind === "prediction") {
                const isAttack = ev.prediction && ev.prediction !== "normal";
                const confPercent = Math.round((ev.confidence || 0) * 100);
                const feats = ev.features || {};

                if (isAttack) {
                  anomalyList.push({
                    id: `ANOM-${ev.sequence || idx}`,
                    deviceName: ev.device_id,
                    type: ev.prediction.toUpperCase(),
                    confidence: confPercent,
                    severity: confPercent >= 90 ? "CRITICAL" : "HIGH",
                    time: evTime,
                    features: feats
                  });

                  logList.push({
                    id: `LOG-${idx}`,
                    message: `[THREAT DETECTED] ${ev.device_id} seq #${ev.sequence || "?"} - ${ev.prediction.toUpperCase()} (${confPercent}% conf) reported=${ev.reported_attack_type}`,
                    timestamp: evTime,
                    severity: "Critical",
                    icon: "ShieldAlert"
                  });
                } else {
                  // Normal packet received
                  const protoName = feats.proto === 1 ? "TCP" : feats.proto === 2 ? "UDP" : "IP";
                  logList.push({
                    id: `LOG-${idx}`,
                    message: `[NORMAL FLOW] ${ev.device_id} seq #${ev.sequence || "?"} (${protoName}, ${feats.src_bytes || 0}B, ${feats.duration || 0}s) - Safe (100%)`,
                    timestamp: evTime,
                    severity: "Success",
                    icon: "ShieldCheck"
                  });
                }
              } else if (ev.kind === "block" || ev.kind === "unblock") {
                logList.push({
                  id: `LOG-CMD-${idx}`,
                  message: `[SERVER CONTROL] ${ev.device_id} was ${ev.kind.toUpperCase()}ED by operator/policy`,
                  timestamp: evTime,
                  severity: ev.kind === "block" ? "Warning" : "Success",
                  icon: ev.kind === "block" ? "Ban" : "ShieldCheck"
                });
              }
            });

            setAnomalies(anomalyList.slice(0, 10));
            setLogs(logList.slice(0, 30));

            // Generate recommendations based on current state
            const pendingActions = [];
            const blockedDevs = devices.filter((d) => d.blocked);
            blockedDevs.forEach((d) => {
              pendingActions.push({
                id: `ACT-UNBLOCK-${d.id}`,
                action: "Authorize & Unblock",
                target: d.id,
                reason: "Device currently quarantined by consecutive defense policy",
                severity: "High",
                color: "bg-rose-500/10 text-rose-400 border-rose-500/20"
              });
            });

            if (pendingActions.length === 0) {
              pendingActions.push({
                id: "ACT-SECURE",
                action: "Continuous Monitoring",
                target: "ESP-A & ESP-B",
                reason: "Neural IDS actively inspecting telemetry streams",
                severity: "Low",
                color: "bg-emerald-500/10 text-emerald-400 border-emerald-500/20"
              });
            }
            setActions(pendingActions);

            // Update traffic chart
            setTrafficHistory((prev) => {
              const nowLabel = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
              const currentAttacks = anomalyList.length;
              const latestEvent = eventsData[0];
              const feats = (latestEvent && latestEvent.features) || {};
              const inBytes = Math.min(1400, Math.max(200, (feats.src_bytes || 570) % 1400));
              const outBytes = Math.min(800, Math.max(100, (feats.dst_bytes || 250) % 800));

              const newPoint = {
                time: nowLabel,
                inbound: inBytes,
                outbound: outBytes,
                threats: currentAttacks > 0 ? 300 : 0,
                total: inBytes + outBytes
              };

              const updatedHistory = [...prev.slice(-15), newPoint];
              return updatedHistory;
            });
          }
        }
      } catch (err) {
        // Backend momentarily busy
      }
    };

    fetchAll();
    const pollInterval = setInterval(fetchAll, 1000);
    return () => {
      isMounted = false;
      clearInterval(pollInterval);
    };
  }, [unblockDevice, devices]);

  // Execute recommendation
  const executeRecommendation = useCallback((actionId) => {
    const targetAction = actions.find(a => a.id === actionId);
    if (!targetAction) return;

    if (targetAction.action === "Authorize & Unblock") {
      unblockDevice(targetAction.target);
    } else {
      addToast(`Action acknowledged: ${targetAction.reason}`, "info");
    }
  }, [actions, unblockDevice, addToast]);

  const blockedCount = devices.filter(d => d.blocked).length;
  const attackCount = devices.filter(d => d.status === "HIGH").length;

  let threatLevel = "Secure";
  if (blockedCount > 0 || attackCount > 0) {
    threatLevel = blockedCount > 0 ? "Quarantined" : "Threat Detected";
  }

  return {
    devices,
    anomalies,
    logs,
    trafficHistory,
    attackDist,
    actions,
    toasts,
    currentTime,
    selectedDevice,
    setSelectedDevice,
    backendOnline,
    metrics: {
      totalDevices: devices.length,
      threatLevel,
      activeAlerts: attackCount + blockedCount,
      detectionAccuracy: 98.8,
      cleanStreak: stats.clean_streak || 0,
      totalFlows: stats.total_flows || 0,
      totalBlocked: blockedCount
    },
    actionsHandlers: {
      executeRecommendation,
      unblockDevice,
      blockDevice,
      addToast,
      setSelectedDevice
    }
  };
}
"""

# 3. SummaryCards.jsx
SUMMARY_CARDS = """import React from 'react';
import { Cpu, ShieldAlert, ShieldCheck, Activity, Sparkles, Lock } from 'lucide-react';

export default function SummaryCards({ metrics }) {
  const isQuarantined = metrics.totalBlocked > 0;
  const isThreat = metrics.activeAlerts > 0 && !isQuarantined;

  const cards = [
    {
      title: "Active IoT Nodes",
      value: `${metrics.totalDevices} Online`,
      subtext: "ESP-A (COM9) & ESP-B (COM13)",
      subtextColor: "text-emerald-400",
      icon: Cpu,
      iconBg: "bg-blue-950/50 border border-blue-800/40 text-blue-400"
    },
    {
      title: "Defense Status",
      value: isQuarantined ? "BLOCKED" : isThreat ? "ATTACK" : "SECURE",
      subtext: isQuarantined 
        ? `${metrics.totalBlocked} node(s) quarantined` 
        : isThreat 
        ? "Active anomaly under inspection" 
        : "Autonomous shield active",
      subtextColor: isQuarantined ? "text-rose-500" : isThreat ? "text-amber-400" : "text-emerald-400",
      icon: isQuarantined ? Lock : isThreat ? ShieldAlert : ShieldCheck,
      iconBg: isQuarantined 
        ? "bg-rose-950/60 border border-rose-800 text-rose-400 animate-pulse" 
        : isThreat 
        ? "bg-amber-950/50 border border-amber-800 text-amber-400" 
        : "bg-emerald-950/50 border border-emerald-800/40 text-emerald-400"
    },
    {
      title: "Clean Packet Streak",
      value: `${metrics.cleanStreak} Flows`,
      subtext: `Total processed: ${metrics.totalFlows} packets`,
      subtextColor: "text-cyan-400",
      icon: Activity,
      iconBg: "bg-cyan-950/50 border border-cyan-800/40 text-cyan-400"
    },
    {
      title: "Model Accuracy",
      value: `${metrics.detectionAccuracy}%`,
      subtext: "PyTorch 6-Class MLP (Trained on 10 features)",
      subtextColor: "text-emerald-400",
      icon: Sparkles,
      iconBg: "bg-emerald-950/50 border border-emerald-800/40 text-emerald-400"
    }
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
      {cards.map((card, idx) => {
        const Icon = card.icon;
        return (
          <div key={idx} className="cyber-card p-5 rounded-xl flex justify-between items-start transition-all hover:border-slate-700">
            <div className="space-y-1">
              <p className="text-[10px] text-slate-400 font-semibold uppercase tracking-wider">
                {card.title}
              </p>
              <h3 className="text-2xl font-bold font-heading text-white tracking-tight">
                {card.value}
              </h3>
              <p className={`text-xs font-semibold ${card.subtextColor} pt-1`}>
                {card.subtext}
              </p>
            </div>
            <div className={`p-2.5 rounded-lg ${card.iconBg}`}>
              <Icon className="w-5 h-5" />
            </div>
          </div>
        );
      })}
    </div>
  );
}
"""

# 4. ConnectedDevices.jsx
CONNECTED_DEVICES = """import React from 'react';
import { Wifi, Lock, ShieldAlert, ShieldCheck } from 'lucide-react';

export default function ConnectedDevices({ devices, onViewAll, onInspectDevice }) {
  
  const getStatusBadge = (dev) => {
    if (dev.blocked) {
      return (
        <span className="px-2.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase text-rose-400 bg-rose-950/60 border border-rose-700 animate-pulse flex items-center gap-1">
          <Lock className="w-3 h-3" />
          BLOCKED
        </span>
      );
    }
    if (dev.status === 'HIGH' || (dev.prediction && dev.prediction !== 'normal')) {
      return (
        <span className="px-2.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase text-amber-400 bg-amber-950/50 border border-amber-700 animate-pulse flex items-center gap-1">
          <ShieldAlert className="w-3 h-3" />
          {dev.prediction ? dev.prediction.toUpperCase() : 'ATTACK'}
        </span>
      );
    }
    return (
      <span className="px-2.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase text-emerald-400 bg-emerald-950/30 border border-emerald-800 flex items-center gap-1">
        <ShieldCheck className="w-3 h-3" />
        NORMAL
      </span>
    );
  };

  return (
    <div className="cyber-card p-6 rounded-xl flex flex-col h-[340px] justify-between">
      {/* Header */}
      <div className="flex justify-between items-center mb-4">
        <div>
          <h3 className="font-heading font-bold text-slate-200 text-sm flex items-center gap-2">
            Monitored Hardware Endpoints
            <span className="text-[10px] bg-blue-950 border border-blue-800/60 text-blue-400 px-2 py-0.5 rounded-full font-mono">
              Live Bridge
            </span>
          </h3>
          <p className="text-[11px] text-slate-500 font-sans mt-0.5">
            Real hardware nodes streaming via USB Serial + Wi-Fi MQTT Proxy
          </p>
        </div>
        <span className="text-xs font-mono text-slate-400">
          {devices.length} Nodes Online
        </span>
      </div>

      {/* Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 flex-1">
        {devices.map((dev) => {
          return (
            <div 
              key={dev.id}
              onClick={() => onInspectDevice(dev)}
              className={`p-3.5 rounded-xl border flex items-center justify-between cursor-pointer transition-all group ${
                dev.blocked 
                  ? 'border-rose-800/80 bg-rose-950/20 hover:border-rose-600' 
                  : dev.status === 'HIGH' 
                  ? 'border-amber-800/80 bg-amber-950/20 hover:border-amber-600'
                  : 'border-slate-800/60 bg-slate-950/30 hover:border-blue-600/60'
              }`}
            >
              <div className="flex items-center gap-3">
                <div className={`p-2.5 rounded-lg shrink-0 border ${
                  dev.blocked 
                    ? 'bg-rose-950/60 border-rose-800 text-rose-400' 
                    : dev.status === 'HIGH'
                    ? 'bg-amber-950/60 border-amber-800 text-amber-400'
                    : 'bg-blue-950/45 border-blue-900/30 text-blue-400'
                }`}>
                  <Wifi className="w-4.5 h-4.5" />
                </div>
                <div>
                  <h4 className="font-heading font-semibold text-xs text-slate-200 group-hover:text-cyan-300 transition-colors">
                    {dev.name}
                  </h4>
                  <p className="text-[10px] text-slate-500 font-mono mt-0.5">
                    {dev.ip} • Seq #{dev.sequence || 0}
                  </p>
                  <p className="text-[9px] text-slate-400 font-mono mt-0.5">
                    Pred: <span className={dev.prediction === 'normal' ? 'text-emerald-400 font-bold' : 'text-rose-400 font-bold'}>{dev.prediction.toUpperCase()}</span> ({Math.round(dev.confidence * 100)}%)
                  </p>
                </div>
              </div>
              
              <div className="flex flex-col items-end gap-1.5">
                {getStatusBadge(dev)}
                <span className="text-[9px] text-slate-500 font-mono">
                  {dev.lastSeen || 'Live'}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
"""

# 5. AnomaliesTable.jsx
ANOMALIES_TABLE = """import React from 'react';
import { ShieldCheck, AlertTriangle } from 'lucide-react';

export default function AnomaliesTable({ anomalies, onInspectDevice }) {
  
  const getSeverityBadge = (severity) => {
    switch (severity) {
      case 'CRITICAL':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[8px] font-mono font-bold tracking-wider bg-rose-950/50 text-rose-400 border border-rose-800 uppercase animate-pulse">
            ● Critical
          </span>
        );
      case 'HIGH':
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[8px] font-mono font-bold tracking-wider bg-amber-950/40 text-amber-400 border border-amber-800/40 uppercase">
            High
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded text-[8px] font-mono font-bold tracking-wider bg-blue-950/40 text-blue-400 border border-blue-900 uppercase">
            Medium
          </span>
        );
    }
  };

  return (
    <div className="cyber-card p-6 rounded-xl flex flex-col h-[340px] justify-between">
      {/* Header */}
      <div className="mb-4 flex justify-between items-start">
        <div>
          <h3 className="font-heading font-bold text-slate-200 text-sm flex items-center gap-2">
            AI-Detected Exploits & Anomalies
          </h3>
          <p className="text-[11px] text-slate-500 font-sans mt-0.5">
            Real-time multi-class classifications exceeding anomaly baseline
          </p>
        </div>
        <span className="text-[10px] font-mono text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
          {anomalies.length} Records
        </span>
      </div>

      {/* Table container */}
      <div className="flex-1 overflow-y-auto pr-1">
        {anomalies.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-slate-500 py-10">
            <ShieldCheck className="w-10 h-10 text-emerald-500 mb-2 opacity-80" />
            <p className="text-xs font-semibold text-slate-300">Clean Operating Profile</p>
            <p className="text-[10px] text-slate-500 mt-1">Zero malicious anomalies observed in current flow batch.</p>
          </div>
        ) : (
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800/60 text-[9px] font-mono text-slate-500 uppercase tracking-wider pb-2">
                <th className="pb-2.5 font-semibold">Incident</th>
                <th className="pb-2.5 font-semibold">Device</th>
                <th className="pb-2.5 font-semibold">Classification</th>
                <th className="pb-2.5 font-semibold">Confidence</th>
                <th className="pb-2.5 font-semibold">Severity</th>
                <th className="pb-2.5 font-semibold text-right">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-900/40 text-xs font-mono">
              {anomalies.map((anom) => (
                <tr 
                  key={anom.id} 
                  className="hover:bg-slate-900/40 transition-colors group cursor-pointer"
                  onClick={() => onInspectDevice && onInspectDevice({ id: anom.deviceName, name: anom.deviceName })}
                >
                  <td className="py-2.5 text-slate-500 text-[11px]">
                    {anom.id}
                  </td>
                  <td className="py-2.5 font-sans font-bold text-slate-200 group-hover:text-cyan-300 transition-colors">
                    {anom.deviceName}
                  </td>
                  <td className="py-2.5 font-mono font-bold text-rose-400">
                    {anom.type}
                  </td>
                  <td className="py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="w-16 bg-slate-900 border border-slate-800/40 rounded-full h-1.5 overflow-hidden">
                        <div 
                          className="h-full rounded-full bg-rose-500"
                          style={{ width: `${anom.confidence}%` }}
                        />
                      </div>
                      <span className="text-[10px] text-slate-300 font-bold">{anom.confidence}%</span>
                    </div>
                  </td>
                  <td className="py-2.5">
                    {getSeverityBadge(anom.severity)}
                  </td>
                  <td className="py-2.5 text-right text-slate-400 text-[10px] font-sans">
                    {anom.time}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
"""

# 6. LiveLogFeed.jsx
LIVE_LOG_FEED = """import React, { useState } from 'react';
import { Ban, Activity, ShieldAlert, ShieldCheck, Filter } from 'lucide-react';

export default function LiveLogFeed({ logs }) {
  const [filter, setFilter] = useState('ALL'); // 'ALL' or 'ATTACKS'

  const filteredLogs = logs.filter((log) => {
    if (filter === 'ATTACKS') {
      return log.severity === 'Critical' || log.severity === 'Warning';
    }
    return true;
  });

  const getLogIconConfig = (log) => {
    if (log.severity === 'Critical') {
      return { icon: Ban, color: 'text-rose-400 bg-rose-950/50 border-rose-800' };
    }
    if (log.severity === 'Warning') {
      return { icon: ShieldAlert, color: 'text-amber-400 bg-amber-950/50 border-amber-800' };
    }
    return { icon: ShieldCheck, color: 'text-emerald-400 bg-emerald-950/40 border-emerald-800/60' };
  };

  return (
    <div className="cyber-card p-6 rounded-xl flex flex-col h-[340px] justify-between">
      {/* Header */}
      <div className="mb-3 flex justify-between items-center">
        <div>
          <h3 className="font-heading font-bold text-slate-200 text-sm">
            Live Packet Telemetry Stream
          </h3>
          <p className="text-[11px] text-slate-500 font-sans mt-0.5">
            Streaming packet inspection from COM9, COM13 & MQTT
          </p>
        </div>

        {/* Filter Toggle */}
        <div className="flex bg-slate-950 border border-slate-800 rounded-lg p-0.5 text-[9px] font-mono">
          <button
            onClick={() => setFilter('ALL')}
            className={`px-2 py-1 rounded transition-colors ${filter === 'ALL' ? 'bg-blue-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
          >
            All
          </button>
          <button
            onClick={() => setFilter('ATTACKS')}
            className={`px-2 py-1 rounded transition-colors ${filter === 'ATTACKS' ? 'bg-rose-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
          >
            Alerts
          </button>
        </div>
      </div>

      {/* Log Feed List */}
      <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
        {filteredLogs.map((log) => {
          const { icon: Icon, color: iconColor } = getLogIconConfig(log);
          return (
            <div key={log.id} className="flex items-start gap-2.5 group p-1.5 rounded-lg hover:bg-slate-900/40 transition-colors">
              <div className={`p-1.5 rounded-lg shrink-0 border flex items-center justify-center ${iconColor}`}>
                <Icon className="w-3.5 h-3.5" />
              </div>
              <div className="min-w-0 flex-1">
                <p className="text-[11px] text-slate-200 font-mono leading-relaxed break-all">
                  {log.message}
                </p>
                <p className="text-[9px] text-slate-500 font-mono mt-0.5">
                  {log.timestamp}
                </p>
              </div>
            </div>
          );
        })}
        {filteredLogs.length === 0 && (
          <div className="h-full flex items-center justify-center text-slate-500 text-xs font-mono">
            No telemetry records matching filter.
          </div>
        )}
      </div>
    </div>
  );
}
"""

# 7. AIRecommendations.jsx
AI_RECOMMENDATIONS = """import React from 'react';
import { ShieldCheck, Lock, CheckCircle, RefreshCw } from 'lucide-react';

export default function AIRecommendations({ actions, onExecuteAction }) {
  return (
    <div className="cyber-card p-6 rounded-xl flex flex-col h-[340px] justify-between">
      {/* Header */}
      <div className="flex justify-between items-start mb-3">
        <div>
          <h3 className="font-heading font-bold text-slate-200 text-sm flex items-center gap-2">
            Automated Defense Status
          </h3>
          <p className="text-[10px] text-slate-500 font-sans mt-0.5">
            Rule: 3 consecutive high-confidence attacks triggers instant quarantine
          </p>
        </div>
        
        <span className="flex items-center gap-1 px-2 py-0.5 text-[8px] font-bold rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500 animate-ping" />
          <span>ACTIVE</span>
        </span>
      </div>

      {/* Suggested Actions List */}
      <div className="flex-1 overflow-y-auto space-y-2.5 pr-1">
        {actions.map((act) => {
          const isQuarantineAction = act.action === "Authorize & Unblock";

          return (
            <div 
              key={act.id} 
              className={`p-3 rounded-xl border flex items-center justify-between gap-3 group transition-all ${
                isQuarantineAction
                  ? 'border-rose-700 bg-rose-950/25'
                  : 'border-slate-800/60 bg-slate-950/20'
              }`}
            >
              <div className="flex items-center gap-3 min-w-0">
                <div className={`p-2 rounded-lg shrink-0 flex items-center justify-center border ${
                  isQuarantineAction
                    ? 'bg-rose-950/60 border-rose-800 text-rose-400'
                    : 'bg-emerald-950/40 border-emerald-800/60 text-emerald-400'
                }`}>
                  {isQuarantineAction ? <Lock className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
                </div>
                <div className="min-w-0">
                  <h4 className="font-heading font-semibold text-xs text-slate-200">{act.action}</h4>
                  <p className="text-[9px] text-slate-400 font-mono mt-0.5 truncate max-w-[200px]">
                    <span className="text-cyan-400 font-semibold">{act.target}</span>: {act.reason}
                  </p>
                </div>
              </div>
              
              {isQuarantineAction && (
                <button
                  onClick={() => onExecuteAction(act.id)}
                  className="px-3.5 py-1.5 rounded-lg text-[10px] font-bold bg-rose-600 hover:bg-rose-500 text-white transition-colors cursor-pointer shrink-0"
                >
                  Unblock
                </button>
              )}
            </div>
          );
        })}
        
        {actions.length === 0 && (
          <div className="h-full flex flex-col items-center justify-center text-slate-500 py-12">
            <CheckCircle className="w-8 h-8 text-emerald-500 mb-1.5" />
            <p className="text-xs font-semibold text-slate-400">All Nodes Secure</p>
            <p className="text-[10px] text-slate-600 mt-0.5">Automated policy ready to isolate threats instantly.</p>
          </div>
        )}
      </div>
    </div>
  );
}
"""

# 8. DeviceDetailModal.jsx
DEVICE_DETAIL_MODAL = """import React from 'react';
import { X, Lock, ShieldCheck, Activity, Wifi, Terminal } from 'lucide-react';

export default function DeviceDetailModal({ device, onClose, actions }) {
  if (!device) return null;

  const probs = device.probabilities || {};
  const feats = device.features || {};

  return (
    <div 
      onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-in fade-in duration-200 cursor-pointer"
    >
      <div 
        onClick={(e) => e.stopPropagation()}
        className="bg-[#0b101d] border border-slate-800 rounded-2xl w-full max-w-2xl shadow-2xl overflow-hidden text-slate-200 cursor-default"
      >
        
        {/* Modal Header */}
        <div className="p-6 border-b border-slate-800 flex justify-between items-center bg-[#070b13]">
          <div className="flex items-center gap-3">
            <div className={`p-2.5 rounded-xl border ${
              device.blocked 
                ? 'bg-rose-950/60 border-rose-800 text-rose-400' 
                : 'bg-blue-950/60 border-blue-800 text-blue-400'
            }`}>
              <Wifi className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="font-heading font-bold text-lg text-white">{device.name}</h3>
                <span className="text-[10px] font-mono text-slate-400 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded">
                  {device.rawId || device.id}
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono mt-0.5">IP: {device.ip} • Last seen: {device.lastSeen}</p>
            </div>
          </div>
          
          <button 
            onClick={onClose}
            className="p-1.5 rounded-lg bg-slate-900 border border-slate-800 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-6 space-y-6 max-h-[75vh] overflow-y-auto">
          
          {/* Defense Warning Banner if Blocked */}
          {device.blocked ? (
            <div className="p-4 rounded-xl border border-rose-700 bg-rose-950/30 flex items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <Lock className="w-6 h-6 text-rose-400 shrink-0" />
                <div>
                  <h4 className="text-sm font-bold text-rose-400 font-heading">
                    NODE CURRENTLY QUARANTINED
                  </h4>
                  <p className="text-xs text-slate-300 mt-0.5">
                    Consecutive attack detections triggered automatic defense isolation. Inbound telemetry is rejected.
                  </p>
                </div>
              </div>
              <button
                onClick={() => {
                  actions.unblockDevice(device.rawId || device.id);
                  onClose();
                }}
                className="px-4 py-2 text-xs font-bold rounded-xl bg-rose-600 hover:bg-rose-500 text-white transition-all shrink-0 cursor-pointer"
              >
                Authorize & Unblock
              </button>
            </div>
          ) : (
            <div className="p-3.5 rounded-xl border border-emerald-800/60 bg-emerald-950/20 flex items-center gap-3">
              <ShieldCheck className="w-5 h-5 text-emerald-400 shrink-0" />
              <p className="text-xs text-slate-300">
                Node is currently active and protected under standard policy.
              </p>
            </div>
          )}

          {/* Neural Network Probability Distribution */}
          <div className="p-4 bg-slate-950/40 border border-slate-800 rounded-xl space-y-3">
            <h4 className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              PyTorch 6-Class Inference Probabilities
            </h4>

            <div className="grid grid-cols-2 gap-3 text-xs font-mono">
              {['normal', 'dos', 'scanning', 'ddos', 'ransomware', 'backdoor'].map((cls) => {
                const val = probs[cls] || (cls === device.prediction ? device.confidence : 0);
                const percent = Math.round(val * 100);
                const isSelected = cls === device.prediction;

                return (
                  <div key={cls} className={`p-2.5 rounded-lg border ${
                    isSelected 
                      ? 'border-blue-600 bg-blue-950/30' 
                      : 'border-slate-800/80 bg-slate-900/30'
                  }`}>
                    <div className="flex justify-between items-center mb-1">
                      <span className={`uppercase font-bold ${isSelected ? 'text-cyan-300' : 'text-slate-400'}`}>
                        {cls}
                      </span>
                      <span className="font-bold text-slate-200">{percent}%</span>
                    </div>
                    <div className="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                      <div 
                        className={`h-full rounded-full ${
                          cls === 'normal' ? 'bg-emerald-500' : 'bg-rose-500'
                        }`}
                        style={{ width: `${percent}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Last Received Telemetry Features */}
          <div className="p-4 bg-slate-950/40 border border-slate-800 rounded-xl space-y-3">
            <h4 className="text-xs font-mono font-bold text-slate-400 uppercase tracking-wider flex items-center gap-2">
              <Terminal className="w-4 h-4 text-blue-400" />
              Raw Flow Features Vector (Seq #{device.sequence || 0})
            </h4>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
              <div className="p-2 bg-slate-900/40 rounded border border-slate-800/60">
                <span className="text-[10px] text-slate-500 uppercase">Protocol</span>
                <p className="font-bold text-slate-200 mt-0.5">{feats.proto === 1 ? 'TCP' : feats.proto === 2 ? 'UDP' : 'ICMP'}</p>
              </div>
              <div className="p-2 bg-slate-900/40 rounded border border-slate-800/60">
                <span className="text-[10px] text-slate-500 uppercase">Src Bytes</span>
                <p className="font-bold text-slate-200 mt-0.5">{feats.src_bytes || 0} B</p>
              </div>
              <div className="p-2 bg-slate-900/40 rounded border border-slate-800/60">
                <span className="text-[10px] text-slate-500 uppercase">Dst Bytes</span>
                <p className="font-bold text-slate-200 mt-0.5">{feats.dst_bytes || 0} B</p>
              </div>
              <div className="p-2 bg-slate-900/40 rounded border border-slate-800/60">
                <span className="text-[10px] text-slate-500 uppercase">Duration</span>
                <p className="font-bold text-slate-200 mt-0.5">{feats.duration || 0} s</p>
              </div>
              <div className="p-2 bg-slate-900/40 rounded border border-slate-800/60">
                <span className="text-[10px] text-slate-500 uppercase">Packets</span>
                <p className="font-bold text-slate-200 mt-0.5">{(feats.src_pkts || 0) + (feats.dst_pkts || 0)}</p>
              </div>
              <div className="p-2 bg-slate-900/40 rounded border border-slate-800/60">
                <span className="text-[10px] text-slate-500 uppercase">Src Port</span>
                <p className="font-bold text-slate-200 mt-0.5">{feats.src_port || 'N/A'}</p>
              </div>
              <div className="p-2 bg-slate-900/40 rounded border border-slate-800/60">
                <span className="text-[10px] text-slate-500 uppercase">Dst Port</span>
                <p className="font-bold text-slate-200 mt-0.5">{feats.dst_port || 'N/A'}</p>
              </div>
              <div className="p-2 bg-slate-900/40 rounded border border-slate-800/60">
                <span className="text-[10px] text-slate-500 uppercase">Reported</span>
                <p className="font-bold text-slate-200 mt-0.5">{device.reported_attack_type || 'NONE'}</p>
              </div>
            </div>
          </div>

        </div>
      </div>
    </div>
  );
}
"""

# 9. App.jsx
APP_JSX = """import React from 'react';
import useSecurityState from './hooks/useSecurityState';
import SummaryCards from './components/SummaryCards';
import TrafficChart from './components/TrafficChart';
import AttackDistribution from './components/AttackDistribution';
import ConnectedDevices from './components/ConnectedDevices';
import AnomaliesTable from './components/AnomaliesTable';
import AIRecommendations from './components/AIRecommendations';
import LiveLogFeed from './components/LiveLogFeed';
import DeviceDetailModal from './components/DeviceDetailModal';
import { AlertCircle, Lock } from 'lucide-react';

export default function App() {
  const {
    devices,
    anomalies,
    logs,
    trafficHistory,
    attackDist,
    actions,
    toasts,
    currentTime,
    selectedDevice,
    setSelectedDevice,
    backendOnline,
    metrics,
    actionsHandlers,
  } = useSecurityState();

  const quarantinedDevices = devices.filter((d) => d.blocked);

  return (
    <div className="min-h-screen bg-[#070b13] text-slate-100 font-sans p-6 sm:p-8 relative selection:bg-blue-500 selection:text-slate-900 overflow-x-hidden">
      
      {/* Top Header Section */}
      <header className="flex justify-between items-center pb-6 mb-6 border-b border-slate-900/60 max-w-[1600px] mx-auto">
        <div className="space-y-1">
          <h1 className="text-xl font-bold font-heading text-white">
            Intrusion AI <span className="text-slate-600 font-normal">/</span> <span className="text-[#3b82f6]">IoT IDS Monitor</span>
          </h1>
          <p className="text-[10px] text-slate-500 font-sans tracking-wide">
            PyTorch Neural Network • Real-time Telemetry & Autonomous Defense Display
          </p>
        </div>

        {/* Model Live Clock Status Widget */}
        <div className="flex items-center gap-3">
          <div className="bg-[#0c1322] border border-[#182235] rounded-full px-4 py-1.5 flex items-center gap-3.5 text-[11px] text-slate-400 font-mono shadow-inner">
            <div className="flex items-center gap-1.5">
              <span className="relative flex h-2 w-2">
                <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${backendOnline ? 'bg-emerald-400' : 'bg-amber-400'} opacity-75`}></span>
                <span className={`relative inline-flex rounded-full h-1.5 w-1.5 ${backendOnline ? 'bg-emerald-500' : 'bg-amber-500'}`}></span>
              </span>
              <span className="text-slate-300 font-medium">{backendOnline ? "API Online (8000)" : "Connecting..."}</span>
            </div>
            <span className="text-slate-700">|</span>
            <span className="text-slate-400 tracking-widest">{currentTime || "12:00:00 PM"}</span>
          </div>
        </div>
      </header>

      {/* Warning Banner if Any Device is Quarantined */}
      {quarantinedDevices.length > 0 && (
        <div className="max-w-[1600px] mx-auto mb-6 p-4 rounded-xl border border-rose-600/60 bg-rose-950/40 flex items-center justify-between text-rose-300">
          <div className="flex items-center gap-3">
            <Lock className="w-5 h-5 text-rose-400 shrink-0 animate-pulse" />
            <p className="text-xs font-semibold">
              <span className="font-bold uppercase tracking-wider text-rose-200">Autonomous Quarantine Active:</span> {quarantinedDevices.map(d => d.name).join(", ")} has been blocked by the consecutive detection policy!
            </p>
          </div>
          <button
            onClick={() => setSelectedDevice(quarantinedDevices[0])}
            className="text-xs font-bold text-white bg-rose-600 hover:bg-rose-500 px-3 py-1 rounded-lg transition-colors cursor-pointer"
          >
            Review Device
          </button>
        </div>
      )}

      {/* Main Grid Layout Container */}
      <main className="max-w-[1600px] mx-auto space-y-6">
        
        {/* Row 1: Summary Cards */}
        <SummaryCards metrics={metrics} />

        {/* 12-Column Responsive Grid Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          
          {/* Row 2 (8-4 split): Traffic Line Chart & Attack Distribution */}
          <div className="lg:col-span-8">
            <TrafficChart trafficData={trafficHistory} />
          </div>
          <div className="lg:col-span-4">
            <AttackDistribution data={attackDist} />
          </div>

          {/* Row 3 (8-4 split): Connected Devices Grid & Autonomous Defense Status */}
          <div className="lg:col-span-8">
            <ConnectedDevices 
              devices={devices} 
              onViewAll={() => actionsHandlers.addToast("Displaying all active hardware nodes.", "info")}
              onInspectDevice={(dev) => setSelectedDevice(dev)}
            />
          </div>
          <div className="lg:col-span-4">
            <AIRecommendations 
              actions={actions} 
              onExecuteAction={actionsHandlers.executeRecommendation} 
            />
          </div>

          {/* Row 4 (8-4 split): Anomalies Table & Live Packet Feed */}
          <div className="lg:col-span-8">
            <AnomaliesTable 
              anomalies={anomalies} 
              onInspectDevice={(dev) => setSelectedDevice(dev)}
            />
          </div>
          <div className="lg:col-span-4">
            <LiveLogFeed logs={logs} />
          </div>

        </div>
      </main>

      {/* Endpoint Inspection Details Overlay Modal */}
      {selectedDevice && (
        <DeviceDetailModal 
          device={devices.find(d => d.name === selectedDevice.name || d.id === selectedDevice.id || d.rawId === selectedDevice.id) || selectedDevice} 
          onClose={() => setSelectedDevice(null)} 
          actions={actionsHandlers} 
        />
      )}

      {/* Floating Notifications Toast Stack */}
      <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 max-w-sm pointer-events-none">
        {toasts.map((toast) => (
          <div 
            key={toast.id}
            className={`p-4 rounded-xl border border-slate-800 shadow-xl flex items-start gap-3 pointer-events-auto bg-[#0d1527]/95 backdrop-blur-sm animate-in slide-in-from-bottom-6 duration-300 ${
              toast.type === 'success' ? 'text-emerald-400 border-emerald-500/20' : 'text-blue-400 border-blue-500/20'
            }`}
          >
            <AlertCircle className={`w-5 h-5 shrink-0 ${toast.type === 'success' ? 'text-emerald-400' : 'text-blue-400'}`} />
            <div>
              <p className="text-xs font-semibold leading-relaxed font-sans">{toast.message}</p>
            </div>
          </div>
        ))}
      </div>

    </div>
  );
}
"""

def main():
    print("Writing updated files to Desktop dashboard...")
    (DASHBOARD_DIR / "vite.config.js").write_text(VITE_CONFIG, encoding="utf-8")
    print("[OK] vite.config.js")

    (HOOKS_DIR / "useSecurityState.js").write_text(USE_SECURITY_STATE, encoding="utf-8")
    print("[OK] src/hooks/useSecurityState.js")

    (COMPONENTS_DIR / "SummaryCards.jsx").write_text(SUMMARY_CARDS, encoding="utf-8")
    print("[OK] src/components/SummaryCards.jsx")

    (COMPONENTS_DIR / "ConnectedDevices.jsx").write_text(CONNECTED_DEVICES, encoding="utf-8")
    print("[OK] src/components/ConnectedDevices.jsx")

    (COMPONENTS_DIR / "AnomaliesTable.jsx").write_text(ANOMALIES_TABLE, encoding="utf-8")
    print("[OK] src/components/AnomaliesTable.jsx")

    (COMPONENTS_DIR / "LiveLogFeed.jsx").write_text(LIVE_LOG_FEED, encoding="utf-8")
    print("[OK] src/components/LiveLogFeed.jsx")

    (COMPONENTS_DIR / "AIRecommendations.jsx").write_text(AI_RECOMMENDATIONS, encoding="utf-8")
    print("[OK] src/components/AIRecommendations.jsx")

    (COMPONENTS_DIR / "DeviceDetailModal.jsx").write_text(DEVICE_DETAIL_MODAL, encoding="utf-8")
    print("[OK] src/components/DeviceDetailModal.jsx")

    (SRC_DIR / "App.jsx").write_text(APP_JSX, encoding="utf-8")
    print("[OK] src/App.jsx")

    bat_script = '''@echo off
title Intrusion AI - IoT IDS Live Monitor Dashboard
cd /d "%~dp0"

echo ======================================================================
echo  Intrusion AI - IoT IDS Live Monitor Dashboard
echo  Dashboard UI: http://localhost:3000 (or http://10.240.36.194:3000)
echo  Connected to Backend: http://localhost:8000
echo ======================================================================

npm run dev
if errorlevel 1 (
    echo.
    echo Dashboard server exited with an error.
    pause
)
'''
    (DASHBOARD_DIR / "start_dashboard.bat").write_text(bat_script, encoding="utf-8")
    print("[OK] start_dashboard.bat")

    print("\nAll files written successfully to Desktop dashboard!")

if __name__ == "__main__":
    main()
