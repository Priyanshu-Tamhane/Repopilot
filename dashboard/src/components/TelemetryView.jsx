import React, { useState } from 'react';
import { Activity, Copy, Check } from 'lucide-react';

export default function TelemetryView({ prometheusText }) {
  const [copied, setCopied] = useState(false);

  const defaultText = `# HELP repopilot_uptime_seconds System uptime in seconds\n# TYPE repopilot_uptime_seconds counter\nrepopilot_uptime_seconds 4320.15\n# HELP repopilot_tasks_total Total tasks executed\n# TYPE repopilot_tasks_total counter\nrepopilot_tasks_total 20\n# HELP repopilot_tasks_success Total successful task executions\n# TYPE repopilot_tasks_success counter\nrepopilot_tasks_success 20\n# HELP repopilot_tokens_total Total LLM tokens processed\nrepopilot_tokens_total{type="input"} 6400\nrepopilot_tokens_total{type="saved"} 5383\n# HELP repopilot_cost_dollars Total estimated LLM cost in USD\nrepopilot_cost_dollars 0.000300\n# HELP repopilot_cache_hits_total Total LLM prompt cache hits\nrepopilot_cache_hits_total 17\n# HELP repopilot_routing_count Total model routing decisions by tier\nrepopilot_routing_count{tier="cheap"} 16\nrepopilot_routing_count{tier="heavy"} 4`;

  const text = prometheusText || defaultText;

  const handleCopy = () => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="glass-card" style={{ padding: '24px', marginBottom: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Activity size={20} className="text-emerald-400" />
            Prometheus Telemetry Stream (GET /metrics)
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            Standard Prometheus text exposition format for system monitoring (Grafana / Datadog)
          </p>
        </div>

        <button 
          onClick={handleCopy}
          className="glass-pill"
          style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#fff', cursor: 'pointer', padding: '6px 12px' }}
        >
          {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
          {copied ? 'Copied' : 'Copy Metrics'}
        </button>
      </div>

      <pre style={{
        background: '#040711',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        borderRadius: '12px',
        padding: '16px',
        fontSize: '0.825rem',
        overflowX: 'auto',
        color: '#94a3b8',
        lineHeight: 1.6,
        maxHeight: '360px',
      }}>
        {text}
      </pre>
    </div>
  );
}
