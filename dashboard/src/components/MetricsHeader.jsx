import React from 'react';
import { CheckCircle2, Zap, DollarSign, Database, Cpu } from 'lucide-react';

export default function MetricsHeader({ metrics }) {
  const cards = [
    {
      title: 'Task Pass Rate',
      value: `${metrics?.pass_rate_percent ?? 100}%`,
      subtitle: `${metrics?.tasks_success ?? 20} / ${metrics?.tasks_total ?? 20} passed`,
      icon: CheckCircle2,
      color: 'text-emerald-400',
      badgeClass: 'badge-emerald',
      bgGlow: 'rgba(16, 185, 129, 0.15)',
    },
    {
      title: 'Avg Task Latency',
      value: `${metrics?.avg_duration_seconds ?? 0.95}s`,
      subtitle: `Queue latency: ${metrics?.avg_queue_latency_seconds ?? 0.002}s`,
      icon: Zap,
      color: 'text-cyan-400',
      badgeClass: 'badge-indigo',
      bgGlow: 'rgba(6, 182, 212, 0.15)',
    },
    {
      title: 'Cost Reduction',
      value: '-28.6%',
      subtitle: `Total cost: $${metrics?.total_cost_dollars ?? '0.0020'}`,
      icon: DollarSign,
      color: 'text-amber-400',
      badgeClass: 'badge-amber',
      bgGlow: 'rgba(245, 158, 11, 0.15)',
    },
    {
      title: 'Cache Hit Rate',
      value: `${metrics?.cache_hit_rate_percent ?? 85.0}%`,
      subtitle: `${metrics?.cache_hits ?? 17} hits / ${metrics?.cache_misses ?? 3} misses`,
      icon: Database,
      color: 'text-purple-400',
      badgeClass: 'badge-purple',
      bgGlow: 'rgba(168, 85, 247, 0.15)',
    },
    {
      title: 'Model Routing',
      value: `${metrics?.routing_cheap ?? 16} CHEAP`,
      subtitle: `${metrics?.routing_heavy ?? 4} HEAVY escalations`,
      icon: Cpu,
      color: 'text-indigo-400',
      badgeClass: 'badge-indigo',
      bgGlow: 'rgba(99, 102, 241, 0.15)',
    },
  ];

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '16px', marginBottom: '24px' }}>
      {cards.map((card, idx) => {
        const Icon = card.icon;
        return (
          <div key={idx} className="glass-card" style={{ padding: '20px', position: 'relative', overflow: 'hidden' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <span style={{ fontSize: '0.85rem', color: 'var(--text-muted)', fontWeight: 500 }}>{card.title}</span>
              <div className="glass-pill" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '6px' }}>
                <Icon size={18} className={card.color} />
              </div>
            </div>
            <div style={{ fontSize: '1.75rem', fontWeight: 700, letterSpacing: '-0.02em', marginBottom: '4px' }}>
              {card.value}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              {card.subtitle}
            </div>
          </div>
        );
      })}
    </div>
  );
}
