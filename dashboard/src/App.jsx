import React, { useState, useEffect } from 'react';
import { Layers, Terminal, Activity, RefreshCw, Cpu, CheckCircle2 } from 'lucide-react';
import MetricsHeader from './components/MetricsHeader';
import AblationTable from './components/AblationTable';
import TaskFeed from './components/TaskFeed';
import RoutingDistribution from './components/RoutingDistribution';
import TelemetryView from './components/TelemetryView';

export default function App() {
  const [activeTab, setActiveTab] = useState('overview');
  const [metrics, setMetrics] = useState(null);
  const [ablationData, setAblationData] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [prometheusText, setPrometheusText] = useState('');
  const [loading, setLoading] = useState(false);
  const [isConnected, setIsConnected] = useState(true);

  const fetchData = async () => {
    setLoading(true);
    try {
      // 1. Fetch telemetry metrics summary
      const resSummary = await fetch('/api/dashboard/summary');
      if (resSummary.ok) {
        const data = await resSummary.json();
        setMetrics(data.telemetry);
        setTasks(data.tasks || []);
        setIsConnected(true);
      }

      // 2. Fetch ablation matrix
      const resAblation = await fetch('/api/dashboard/ablation');
      if (resAblation.ok) {
        const data = await resAblation.json();
        setAblationData(data);
      }

      // 3. Fetch raw Prometheus metrics
      const resPrometheus = await fetch('/metrics');
      if (resPrometheus.ok) {
        const text = await resPrometheus.text();
        setPrometheusText(text);
      }
    } catch (err) {
      console.warn('Backend connection fallback to mock preview data:', err);
      setIsConnected(false);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // 5s auto refresh
    return () => clearInterval(interval);
  }, []);

  return (
    <div style={{ maxWidth: '1280px', margin: '0 auto', padding: '32px 24px' }}>
      {/* Header Bar */}
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '32px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '6px' }}>
            <div style={{
              width: '40px',
              height: '40px',
              borderRadius: '12px',
              background: 'linear-gradient(135deg, #6366f1 0%, #06b6d4 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              boxShadow: '0 0 20px rgba(99, 102, 241, 0.4)',
            }}>
              <Cpu size={24} color="#fff" />
            </div>
            <h1 style={{ fontSize: '1.75rem', fontWeight: 700, letterSpacing: '-0.02em', background: 'linear-gradient(90deg, #fff, #94a3b8)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent' }}>
              RepoPilot Command Center
            </h1>
            <span className="glass-pill badge-indigo">Phase 7 • React Dashboard</span>
          </div>
          <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)' }}>
            Evaluation-driven coding-agent infrastructure with dynamic model routing, caching & parallel scaling
          </p>
        </div>

        {/* Action / Refresh controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div className="glass-pill" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: isConnected ? '#10b981' : '#f59e0b' }}></span>
            <span style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>
              {isConnected ? 'API Connected (Live 5s)' : 'Demo Preview Mode'}
            </span>
          </div>

          <button 
            onClick={fetchData}
            className="glass-pill"
            style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#fff', cursor: 'pointer', padding: '8px 16px', background: 'rgba(99, 102, 241, 0.2)', borderColor: 'rgba(99, 102, 241, 0.4)' }}
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Refresh
          </button>
        </div>
      </header>

      {/* Real-time KPI Metric Summary Cards */}
      <MetricsHeader metrics={metrics} />

      {/* Navigation Tabs */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '24px', borderBottom: '1px solid var(--border-color)', paddingBottom: '12px' }}>
        <button
          onClick={() => setActiveTab('overview')}
          style={{
            background: activeTab === 'overview' ? 'rgba(99, 102, 241, 0.25)' : 'transparent',
            border: activeTab === 'overview' ? '1px solid rgba(99, 102, 241, 0.4)' : 'none',
            color: activeTab === 'overview' ? '#fff' : 'var(--text-muted)',
            padding: '8px 16px',
            borderRadius: '8px',
            cursor: 'pointer',
            fontSize: '0.875rem',
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            transition: 'all 0.2s ease',
          }}
        >
          <Layers size={16} /> Overview & Routing
        </button>

        <button
          onClick={() => setActiveTab('ablation')}
          style={{
            background: activeTab === 'ablation' ? 'rgba(99, 102, 241, 0.25)' : 'transparent',
            border: activeTab === 'ablation' ? '1px solid rgba(99, 102, 241, 0.4)' : 'none',
            color: activeTab === 'ablation' ? '#fff' : 'var(--text-muted)',
            padding: '8px 16px',
            borderRadius: '8px',
            cursor: 'pointer',
            fontSize: '0.875rem',
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            transition: 'all 0.2s ease',
          }}
        >
          <CheckCircle2 size={16} /> Ablation Matrix (Exp 1-6)
        </button>

        <button
          onClick={() => setActiveTab('feed')}
          style={{
            background: activeTab === 'feed' ? 'rgba(99, 102, 241, 0.25)' : 'transparent',
            border: activeTab === 'feed' ? '1px solid rgba(99, 102, 241, 0.4)' : 'none',
            color: activeTab === 'feed' ? '#fff' : 'var(--text-muted)',
            padding: '8px 16px',
            borderRadius: '8px',
            cursor: 'pointer',
            fontSize: '0.875rem',
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            transition: 'all 0.2s ease',
          }}
        >
          <Terminal size={16} /> Task Queue & Diffs
        </button>

        <button
          onClick={() => setActiveTab('telemetry')}
          style={{
            background: activeTab === 'telemetry' ? 'rgba(99, 102, 241, 0.25)' : 'transparent',
            border: activeTab === 'telemetry' ? '1px solid rgba(99, 102, 241, 0.4)' : 'none',
            color: activeTab === 'telemetry' ? '#fff' : 'var(--text-muted)',
            padding: '8px 16px',
            borderRadius: '8px',
            cursor: 'pointer',
            fontSize: '0.875rem',
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            transition: 'all 0.2s ease',
          }}
        >
          <Activity size={16} /> Prometheus Metrics
        </button>
      </div>

      {/* Tab Content Rendering */}
      {activeTab === 'overview' && (
        <>
          <RoutingDistribution telemetry={metrics} />
          <AblationTable ablationData={ablationData} />
          <TaskFeed tasks={tasks} />
        </>
      )}

      {activeTab === 'ablation' && (
        <AblationTable ablationData={ablationData} />
      )}

      {activeTab === 'feed' && (
        <TaskFeed tasks={tasks} />
      )}

      {activeTab === 'telemetry' && (
        <TelemetryView prometheusText={prometheusText} />
      )}
    </div>
  );
}
