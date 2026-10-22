import React from 'react';
import { Cpu, Users, Server, Shield } from 'lucide-react';

export default function RoutingDistribution({ telemetry }) {
  const cheapCount = telemetry?.routing_cheap ?? 16;
  const heavyCount = telemetry?.routing_heavy ?? 4;
  const total = cheapCount + heavyCount || 20;

  const cheapPct = Math.round((cheapCount / total) * 100);
  const heavyPct = 100 - cheapPct;

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px', marginBottom: '24px' }}>
      {/* Model Routing Breakdown */}
      <div className="glass-card" style={{ padding: '20px' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Cpu size={18} className="text-amber-400" />
          Dynamic Model Routing Breakdown (Phase 5)
        </h3>
        
        <div style={{ marginBottom: '16px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '6px' }}>
            <span>Tier 1: CHEAP (gpt-oss-20b)</span>
            <span>{cheapPct}% ({cheapCount} tasks)</span>
          </div>
          <div style={{ height: '8px', background: 'rgba(255, 255, 255, 0.05)', borderRadius: '4px', overflow: 'hidden' }}>
            <div style={{ width: `${cheapPct}%`, height: '100%', background: '#f59e0b', borderRadius: '4px' }}></div>
          </div>
        </div>

        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '6px' }}>
            <span>Tier 2: HEAVY Escalation (gpt-oss-120b)</span>
            <span>{heavyPct}% ({heavyCount} tasks)</span>
          </div>
          <div style={{ height: '8px', background: 'rgba(255, 255, 255, 0.05)', borderRadius: '4px', overflow: 'hidden' }}>
            <div style={{ width: `${heavyPct}%`, height: '100%', background: '#a855f7', borderRadius: '4px' }}></div>
          </div>
        </div>

        <div style={{ marginTop: '16px', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
          Routing policy: Keyword complexity & context size threshold (0.50). Escalates to HEAVY on iteration 2 if pytest fails.
        </div>
      </div>

      {/* Worker Pool & Queue State */}
      <div className="glass-card" style={{ padding: '20px' }}>
        <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Server size={18} className="text-purple-400" />
          Worker Pool & Concurrency (Phase 6)
        </h3>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px', marginBottom: '12px' }}>
          <div style={{ background: 'rgba(255, 255, 255, 0.03)', padding: '12px', borderRadius: '8px' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Active Workers</div>
            <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#c084fc' }}>4 Workers</div>
          </div>
          <div style={{ background: 'rgba(255, 255, 255, 0.03)', padding: '12px', borderRadius: '8px' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Queue Wait Time</div>
            <div style={{ fontSize: '1.25rem', fontWeight: 700, color: '#38bdf8' }}>0.002s</div>
          </div>
        </div>

        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Shield size={14} className="text-emerald-400" />
          Isolated temporary git worktrees prevent worker sandbox collisions.
        </div>
      </div>
    </div>
  );
}
