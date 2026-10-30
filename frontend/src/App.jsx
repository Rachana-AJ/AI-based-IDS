import React, { useState, useEffect, useRef, useCallback } from "react";
import "./App.css";

// Skylearn 6 Classes
const CLASSES = [
  { id: "normal", name: "Normal Traffic", color: "var(--leaf)", fillClass: "normal" },
  { id: "dos", name: "Denial of Service (DoS)", color: "var(--coral)", fillClass: "dos" },
  { id: "ddos", name: "Distributed DoS", color: "var(--berry)", fillClass: "ddos" },
  { id: "scanning", name: "Port Scanning", color: "var(--sun)", fillClass: "scanning" },
  { id: "ransomware", name: "Ransomware Burst", color: "#e11d48", fillClass: "ransomware" },
  { id: "backdoor", name: "Backdoor Channel", color: "#0284c7", fillClass: "backdoor" },
];

export default function App() {
  const [viewMode, setViewMode] = useState("guardian"); // 'guardian' or 'inspector'
  const [devices, setDevices] = useState([
    {
      device_id: "ESP-A",
      device_status: "ONLINE",
      state: "NORMAL",
      blocked: false,
      prediction: "normal",
      confidence: 1.0,
      reported_attack_type: "NONE",
      probabilities: { normal: 1.0, dos: 0.0, ddos: 0.0, scanning: 0.0, ransomware: 0.0, backdoor: 0.0 },
      features: { proto: "tcp", src_bytes: 573, dst_bytes: 1420, src_pkts: 5, dst_pkts: 6, duration: 0.05 },
      port: "COM9",
      ip: "10.240.36.183",
    },
    {
      device_id: "ESP-B",
      device_status: "ONLINE",
      state: "NORMAL",
      blocked: false,
      prediction: "normal",
      confidence: 1.0,
      reported_attack_type: "NONE",
      probabilities: { normal: 1.0, dos: 0.0, ddos: 0.0, scanning: 0.0, ransomware: 0.0, backdoor: 0.0 },
      features: { proto: "tcp", src_bytes: 573, dst_bytes: 0, src_pkts: 2, dst_pkts: 0, duration: 0.001 },
      port: "COM13",
      ip: "10.240.36.120",
    },
  ]);

  const [stats, setStats] = useState({
    total_flows: 1420,
    clean_streak: 284,
    total_attacks: 0,
    total_blocked: 0,
    class_counts: { normal: 1420, dos: 0, ddos: 0, scanning: 0, ransomware: 0, backdoor: 0 },
  });

  const [events, setEvents] = useState([]);
  const [isConnected, setIsConnected] = useState(true);
  const [toast, setToast] = useState(null);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const canvasRef = useRef(null);

  // Trigger Skylearn Confetti (Sky, Sun, Leaf, Berry)
  const fireConfetti = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    canvas.width = window.innerWidth;
    canvas.height = window.innerHeight;

    const colors = ["#3B82F6", "#FBBF24", "#22C55E", "#A855F7", "#60A5FA", "#FCD34D"];
    const particles = Array.from({ length: 60 }).map(() => ({
      x: Math.random() * canvas.width,
      y: -10,
      size: Math.random() * 8 + 6,
      color: colors[Math.floor(Math.random() * colors.length)],
      vx: (Math.random() - 0.5) * 4,
      vy: Math.random() * 4 + 3,
      rotation: Math.random() * 360,
      vRot: (Math.random() - 0.5) * 10,
    }));

    let startTime = performance.now();
    const animate = (now) => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const progress = (now - startTime) / 1600; // 1.6s duration
      if (progress >= 1) return;

      particles.forEach((p) => {
        p.x += p.vx;
        p.y += p.vy;
        p.rotation += p.vRot;
        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate((p.rotation * Math.PI) / 180);
        ctx.fillStyle = p.color;
        ctx.globalAlpha = 1 - progress;
        ctx.fillRect(-p.size / 2, -p.size / 2, p.size, p.size);
        ctx.restore();
      });
      requestAnimationFrame(animate);
    };
    requestAnimationFrame(animate);
  }, []);

  const showToast = useCallback((msg) => {
    setToast(msg);
    setTimeout(() => setToast(null), 2500);
  }, []);

  // Speak aloud with SpeechSynthesis
  const speakText = useCallback((text) => {
    if (!("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1.0;
    utterance.pitch = 1.05;
    window.speechSynthesis.speak(utterance);
  }, []);

  // Fetch telemetry & status from FastAPI backend
  const fetchData = useCallback(async () => {
    try {
      const [devRes, statsRes, eventsRes] = await Promise.all([
        fetch("/api/devices"),
        fetch("/api/stats"),
        fetch("/api/events?limit=20"),
      ]);

      if (devRes.ok) {
        const devData = await devRes.json();
        if (devData && devData.length > 0) {
          setDevices((prev) =>
            devData.map((d) => ({
              ...d,
              port: d.device_id === "ESP-A" ? "COM9" : "COM13",
              ip: d.device_id === "ESP-A" ? "10.240.36.183" : "10.240.36.120",
              probabilities: d.probabilities || { normal: 1.0 },
            }))
          );
        }
      }
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }
      if (eventsRes.ok) {
        const eventsData = await eventsRes.json();
        setEvents(eventsData);
      }
      setIsConnected(true);
    } catch {
      setIsConnected(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 1200);
    return () => clearInterval(interval);
  }, [fetchData]);

  // Send Command to Device
  const handleCommand = async (deviceId, command) => {
    try {
      showToast(`${deviceId} ➜ Sending ${command}...`);
      const res = await fetch(`/api/devices/${deviceId}/command`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ command }),
      });
      if (res.ok) {
        showToast(`${deviceId} ➜ Command ${command} acknowledged!`);
        if (command === "UNBLOCK" || command === "NORMAL") {
          fireConfetti();
        }
        if (soundEnabled) {
          speakText(`Command ${command} sent to ${deviceId}`);
        }
        fetchData();
      } else {
        showToast(`Error executing ${command}`);
      }
    } catch (err) {
      showToast(`Network error: ${err.message}`);
    }
  };

  // Browser-side test flow simulation
  const handleSimulate = async (deviceId, attackType) => {
    try {
      showToast(`Simulating ${attackType} on ${deviceId}...`);
      const res = await fetch("/api/simulate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: deviceId, attack_type: attackType }),
      });
      if (res.ok) {
        const data = await res.json();
        showToast(`AI Classified: ${data.prediction.toUpperCase()} (${(data.confidence * 100).toFixed(1)}%)`);
        fetchData();
      }
    } catch (err) {
      showToast(`Sim error: ${err.message}`);
    }
  };

  // Compute mascot text dynamically
  const anyAttack = devices.some((d) => d.state === "ATTACK" || (d.prediction && d.prediction !== "normal"));
  const anyBlocked = devices.some((d) => d.blocked);

  let mascotTitle = "Shield Guardian: All Clear!";
  let mascotText = `Everything looks safe and healthy! Both ESP nodes are transmitting regular telemetry. ${stats.clean_streak} consecutive flows have been verified clean.`;

  if (anyBlocked) {
    mascotTitle = "Shield Guardian: Threat Quarantined";
    mascotText = "An IoT node triggered 3 consecutive high-confidence alerts and was isolated with auto-defense to safeguard your network.";
  } else if (anyAttack) {
    const attackDev = devices.find((d) => d.state === "ATTACK" || d.prediction !== "normal");
    mascotTitle = `Notice: Threat Pattern Detected on ${attackDev?.device_id || "Node"}`;
    mascotText = `The PyTorch neural engine observed a high-frequency packet burst. Flow matches ${attackDev?.prediction?.toUpperCase() || "ATTACK"} signature with ${((attackDev?.confidence || 0.99) * 100).toFixed(1)}% confidence.`;
  }

  return (
    <div className="app-wrapper">
      <canvas
        ref={canvasRef}
        style={{
          position: "fixed",
          top: 0,
          left: 0,
          pointerEvents: "none",
          zIndex: 9999,
          width: "100%",
          height: "100%",
        }}
      />

      {/* Navigation Header */}
      <nav className="navbar" role="navigation" aria-label="Main Navigation">
        <div className="nav-content">
          <a href="#home" className="brand">
            <div className="brand-icon" aria-hidden="true">🛡️</div>
            <div>
              <span className="brand-title">Skylearn IoT</span>
              <span className="brand-badge">Neural Shield</span>
            </div>
          </a>

          <div className="nav-actions">
            {/* Clean Shield Streak Pill */}
            <div className="streak-pill" title="Consecutive safe network flows verified clean">
              <span className="streak-flame" aria-hidden="true">🔥</span>
              <span>{stats.clean_streak} Safe Streak</span>
            </div>

            {/* Broker Status Pill */}
            <div className="status-pill">
              <span className={`status-dot ${isConnected ? "" : "offline"}`} />
              <span>{isConnected ? "Broker & Model Active" : "Connecting..."}</span>
            </div>

            {/* View Mode Switcher */}
            <div className="view-switcher" role="radiogroup" aria-label="Dashboard View Mode">
              <button
                className={`view-btn ${viewMode === "guardian" ? "active" : ""}`}
                onClick={() => setViewMode("guardian")}
                id="btn-guardian-view"
              >
                🌱 Guardian View
              </button>
              <button
                className={`view-btn ${viewMode === "inspector" ? "active" : ""}`}
                onClick={() => setViewMode("inspector")}
                id="btn-inspector-view"
              >
                🔬 Inspector Lab
              </button>
            </div>

            {/* Speech Read-Aloud Button */}
            <button
              className="icon-btn"
              title={soundEnabled ? "Voice Alerts On (Click to Mute)" : "Click to Enable Friendly Voice Alerts"}
              onClick={() => {
                const next = !soundEnabled;
                setSoundEnabled(next);
                if (next) speakText(mascotText);
              }}
              aria-label="Toggle voice alerts"
            >
              {soundEnabled ? "🔊" : "🔈"}
            </button>
          </div>
        </div>
      </nav>

      <main className="main-container">
        {/* Help / Mascot Speech Bubble */}
        <section className="mascot-banner animate-fade" aria-live="polite">
          <div className="mascot-avatar" aria-hidden="true">
            {anyBlocked ? "🔒" : anyAttack ? "⚠️" : "🤖"}
          </div>
          <div className="mascot-body">
            <h2 className="mascot-title">{mascotTitle}</h2>
            <p className="mascot-text">{mascotText}</p>
          </div>
          <button
            className="mascot-action-btn"
            onClick={() => speakText(mascotText)}
            title="Read summary aloud"
          >
            🗣️ Read Aloud
          </button>
        </section>

        {/* Hero Metrics Strip */}
        <section className="metrics-grid" aria-label="System Metrics">
          <div className="metric-card">
            <div className="metric-icon-wrap leaf">🛡️</div>
            <div className="metric-info">
              <span className="metric-label">Clean Shield Streak</span>
              <span className="metric-val">{stats.clean_streak} pkts</span>
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-icon-wrap sky">🧠</div>
            <div className="metric-info">
              <span className="metric-label">PyTorch Neural Model</span>
              <span className="metric-val">6 Classes</span>
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-icon-wrap sun">⚡</div>
            <div className="metric-info">
              <span className="metric-label">Total Flows Evaluated</span>
              <span className="metric-val">{stats.total_flows}</span>
            </div>
          </div>

          <div className="metric-card">
            <div className="metric-icon-wrap coral">🚨</div>
            <div className="metric-info">
              <span className="metric-label">Threats Mitigated</span>
              <span className="metric-val">{stats.total_attacks}</span>
            </div>
          </div>
        </section>

        {/* Hardware Node Cards */}
        <section aria-labelledby="hardware-nodes-heading">
          <div className="nodes-section-title">
            <h2 id="hardware-nodes-heading">📶 Active IoT Hardware Nodes</h2>
            <span style={{ fontSize: "0.9rem", color: "var(--ink-muted)", fontWeight: 600 }}>
              Auto-defense: Quarantines upon 3 consecutive alerts ≥ 90%
            </span>
          </div>

          <div className="nodes-grid">
            {devices.map((dev) => {
              const isNormal = !dev.blocked && dev.state !== "ATTACK" && dev.prediction === "normal";
              const isBlocked = dev.blocked;
              const cardClass = isBlocked
                ? "active-blocked"
                : !isNormal
                ? "active-attack"
                : "active-safe";

              return (
                <article key={dev.device_id} className={`node-card ${cardClass}`} id={`card-${dev.device_id}`}>
                  {/* Card Header */}
                  <div className="node-header">
                    <div className="node-title-group">
                      <div className="node-avatar">
                        {dev.device_id === "ESP-A" ? "🌱" : "🌿"}
                      </div>
                      <div>
                        <h3 className="node-name">{dev.device_id} (Node {dev.device_id === "ESP-A" ? "1" : "2"})</h3>
                        <div className="node-meta">
                          <span>{dev.port}</span> • <span>{dev.ip}</span> • <span>1884 MQTT</span>
                        </div>
                      </div>
                    </div>

                    {/* Status Pill Badge */}
                    <span
                      className={`badge-pill ${
                        isBlocked
                          ? "badge-blocked"
                          : dev.state === "ATTACK" || dev.prediction !== "normal"
                          ? "badge-attack"
                          : "badge-normal"
                      }`}
                    >
                      {isBlocked
                        ? "QUARANTINED"
                        : dev.state === "ATTACK" || dev.prediction !== "normal"
                        ? "INTRUSION ALERT"
                        : "SECURE (NORMAL)"}
                    </span>
                  </div>

                  {/* Flow Rate Strip (Skylearn Progress Bar style) */}
                  <div className="flow-strip-group">
                    <div className="flow-strip-labels">
                      <span>Telemetry Health Strip</span>
                      <span>{isBlocked ? "Isolated" : isNormal ? "100% Verified" : "Anomaly Detected"}</span>
                    </div>
                    <div className="flow-track">
                      <div
                        className={`flow-fill ${!isNormal ? "attack" : ""}`}
                        style={{ width: isBlocked ? "20%" : isNormal ? "100%" : "85%" }}
                      />
                    </div>
                  </div>

                  {/* Prediction & Confidence Summary */}
                  <div className="pred-box">
                    <div className="pred-row">
                      <span className="pred-label">PyTorch Classification:</span>
                      <span className={`pred-val ${isNormal ? "normal" : "attack"}`}>
                        {dev.prediction?.toUpperCase() || "NORMAL"} (
                        {((dev.confidence || 1.0) * 100).toFixed(1)}%)
                      </span>
                    </div>
                    <p className="pred-explanation">
                      {isNormal
                        ? "Flow features conform to normal IoT sensor transmission benchmarks."
                        : `Traffic pattern flagged as ${dev.prediction?.toUpperCase()} attack. Red LED triggers if quarantined.`}
                    </p>
                  </div>

                  {/* Big Friendly Button Grid for Attack & Normal Triggers */}
                  <div className="btn-grid">
                    <button
                      className="btn-cta btn-dos"
                      onClick={() => handleCommand(dev.device_id, "ATTACK:DOS")}
                      title="Trigger DoS volumetric flood"
                      id={`btn-dos-${dev.device_id}`}
                    >
                      🔴 DoS Attack
                    </button>

                    <button
                      className="btn-cta btn-scan"
                      onClick={() => handleCommand(dev.device_id, "ATTACK:SCANNING")}
                      title="Trigger Port Reconnaissance Scan"
                      id={`btn-scan-${dev.device_id}`}
                    >
                      ⚡ Port Scan
                    </button>

                    <button
                      className="btn-cta btn-ddos"
                      onClick={() => handleCommand(dev.device_id, "ATTACK:DDOS")}
                      title="Trigger Distributed DoS flood"
                      id={`btn-ddos-${dev.device_id}`}
                    >
                      💥 DDoS Flood
                    </button>

                    <button
                      className="btn-cta btn-ransom"
                      onClick={() => handleCommand(dev.device_id, "ATTACK:RANSOMWARE")}
                      title="Trigger Ransomware packet burst"
                      id={`btn-ransom-${dev.device_id}`}
                    >
                      🔒 Ransomware
                    </button>

                    <button
                      className="btn-cta btn-normal"
                      onClick={() => handleCommand(dev.device_id, "NORMAL")}
                      title="Return node to standard safe traffic"
                      id={`btn-normal-${dev.device_id}`}
                    >
                      🟢 Restore Normal Traffic
                    </button>

                    <button
                      className="btn-cta btn-unblock"
                      onClick={() => handleCommand(dev.device_id, "UNBLOCK")}
                      title="Clear quarantine defense lock"
                      id={`btn-unblock-${dev.device_id}`}
                    >
                      🔓 Reset / Unblock Quarantine
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        </section>

        {/* Inspector Lab Mode (Deep Neural Probability Bars & Live Event Well) */}
        {viewMode === "inspector" && (
          <section className="inspector-panel animate-fade" aria-label="Inspector Lab">
            <div className="inspector-header">
              <div>
                <h2>🔬 Inspector Lab: Multi-Class Probability Radar</h2>
                <p style={{ color: "var(--ink-muted)", fontSize: "0.95rem" }}>
                  Real-time softmax probability output across all 6 model classes for ESP-A.
                </p>
              </div>
              <div style={{ display: "flex", gap: "10px" }}>
                <button
                  className="mascot-action-btn"
                  onClick={() => handleSimulate("ESP-A", "DOS")}
                  id="btn-sim-dos"
                >
                  🧪 Test DoS Flow
                </button>
                <button
                  className="mascot-action-btn"
                  onClick={() => handleSimulate("ESP-A", "NORMAL")}
                  id="btn-sim-normal"
                >
                  🧪 Test Normal Flow
                </button>
              </div>
            </div>

            {/* Probability Radar Grid */}
            <div className="radar-bars-grid">
              {CLASSES.map((cls) => {
                const espA = devices.find((d) => d.device_id === "ESP-A");
                const prob = espA?.probabilities?.[cls.id] || (cls.id === "normal" ? 1.0 : 0.0);
                const pct = (prob * 100).toFixed(1);

                return (
                  <div key={cls.id} className="prob-tile">
                    <div className="prob-name">
                      <span>{cls.name}</span>
                      <span>{pct}%</span>
                    </div>
                    <div className="prob-track">
                      <div
                        className={`prob-fill ${cls.fillClass}`}
                        style={{ width: `${Math.max(4, Math.min(100, pct))}%` }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Live Telemetry Flow Table Well */}
            <h3 style={{ marginBottom: "12px", fontSize: "1.1rem" }}>📋 Live Telemetry Events & Flow Features</h3>
            <div className="telemetry-well">
              <table className="events-table">
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Node</th>
                    <th>Event Kind</th>
                    <th>Prediction</th>
                    <th>Confidence</th>
                    <th>Reported Type</th>
                    <th>Features Summary</th>
                  </tr>
                </thead>
                <tbody>
                  {events.length === 0 ? (
                    <tr>
                      <td colSpan={7} style={{ textAlign: "center", padding: "20px" }}>
                        Waiting for telemetry streams... Tap any attack or normal button above to evaluate.
                      </td>
                    </tr>
                  ) : (
                    events.slice(0, 10).map((ev, i) => {
                      const isNorm = ev.prediction === "normal";
                      const f = ev.features || {};
                      let protoLabel = "TCP";
                      if (typeof f.proto === "string") {
                        protoLabel = f.proto.toUpperCase();
                      } else if (f.proto === 2) {
                        protoLabel = "UDP";
                      } else if (f.proto === 1) {
                        protoLabel = "TCP";
                      } else if (f.proto !== undefined) {
                        protoLabel = `PROTO-${f.proto}`;
                      }
                      const fStr = f.proto !== undefined
                        ? `${protoLabel} | ${f.src_bytes || 0}B in | ${f.dst_bytes || 0}B out | ${f.src_pkts || 0} pkts`
                        : "Status ping";

                      return (
                        <tr key={i}>
                          <td>{ev.timestamp ? ev.timestamp.substring(11, 19) : "Just now"}</td>
                          <td style={{ fontWeight: 700 }}>{ev.device_id}</td>
                          <td>{ev.kind}</td>
                          <td style={{ color: isNorm ? "var(--leaf-deep)" : "var(--coral-deep)", fontWeight: 700 }}>
                            {ev.prediction ? ev.prediction.toUpperCase() : ev.status || "OK"}
                          </td>
                          <td>{ev.confidence ? `${(ev.confidence * 100).toFixed(1)}%` : "N/A"}</td>
                          <td>{ev.reported_attack_type || "NONE"}</td>
                          <td style={{ color: "var(--ink-muted)" }}>{fStr}</td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </main>

      {/* Toast Alert */}
      {toast && (
        <div className="toast-bar" role="status">
          <span>🔔</span>
          <span>{toast}</span>
        </div>
      )}

      {/* Footer */}
      <footer className="footer-note">
        Skylearn IoT Design System • PyTorch 6-Class Multi-layer Perceptron • Node Nodes: COM9 & COM13 • Local Port 1884 Proxy
      </footer>
    </div>
  );
}
