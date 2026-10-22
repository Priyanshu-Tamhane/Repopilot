import React, { useState } from 'react';
import { Terminal, CheckCircle, AlertTriangle, ChevronDown, ChevronRight, FileCode, GitCommit, Search } from 'lucide-react';

export default function TaskFeed({ tasks }) {
  const [expandedId, setExpandedId] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const defaultTasks = [
    {
      id: 'task-001',
      issue: 'Fix add() in calculator.py: returns wrong value for negative numbers like add(2, -3)',
      repo: './demo_repo',
      status: 'done',
      success: true,
      testsPassed: 2,
      testsFailed: 0,
      durationSeconds: 1.01,
      modelTier: 'CHEAP (mock-gpt-4o-mini-cheap)',
      complexityScore: 0.0,
      cost: '$0.00010',
      patch: `diff --git a/calculator.py b/calculator.py\nindex 030b03a..b65de30 100644\n--- a/calculator.py\n+++ b/calculator.py\n@@ -1,5 +1,5 @@\n def add(a, b):\n     # bug: subtraction instead of addition for negatives\n     if b < 0:\n-        return a - b\n+        return a + b\n     return a + b`,
      spans: [
        { name: 'Issue Diagnosis & Planning (Planner)', duration: 0.05, status: 'ok' },
        { name: 'AST & TF-IDF Retrieval (Researcher)', duration: 0.12, status: 'ok' },
        { name: 'Dynamic Model Routing (CHEAP Tier)', duration: 0.01, status: 'ok' },
        { name: 'Implementation & Sandbox Pytest (Implementer)', duration: 0.75, status: 'ok' },
        { name: 'Git Patch Review & Invariant Gate (Reviewer)', duration: 0.08, status: 'ok' }
      ]
    },
    {
      id: 'task-002',
      issue: 'Fix deadlock and concurrency race condition in process_items recursion algorithm',
      repo: './demo_repo',
      status: 'done',
      success: true,
      testsPassed: 3,
      testsFailed: 0,
      durationSeconds: 1.45,
      modelTier: 'HEAVY (mock-gpt-4o-mini)',
      complexityScore: 0.72,
      cost: '$0.00045',
      patch: `diff --git a/concurrency_queue.py b/concurrency_queue.py\nindex 42a1b9c..91f2a11 100644\n--- a/concurrency_queue.py\n+++ b/concurrency_queue.py\n@@ -5,3 +5,3 @@ def process_items(items):\n-    for i in range(len(items) - 1):\n+    for i in range(len(items)):\n         results.append(items[i] * 2)`,
      spans: [
        { name: 'Issue Diagnosis & Planning (Planner)', duration: 0.10, status: 'ok' },
        { name: 'AST & Dependency Graph Retrieval (Researcher)', duration: 0.20, status: 'ok' },
        { name: 'Dynamic Model Routing (HEAVY Tier Escalation)', duration: 0.02, status: 'ok' },
        { name: 'Implementation Iteration 1 & Pytest (Implementer)', duration: 1.05, status: 'ok' },
        { name: 'Git Patch Review (Reviewer)', duration: 0.08, status: 'ok' }
      ]
    }
  ];

  const items = (tasks && tasks.length > 0) ? tasks : defaultTasks;

  const filteredItems = items.filter(t => {
    const matchesSearch = t.issue.toLowerCase().includes(searchTerm.toLowerCase()) || t.id.toLowerCase().includes(searchTerm.toLowerCase());
    const matchesStatus = statusFilter === 'all' || (statusFilter === 'passed' && t.success) || (statusFilter === 'failed' && !t.success);
    return matchesSearch && matchesStatus;
  });

  return (
    <div className="glass-card" style={{ padding: '24px', marginBottom: '24px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 600, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Terminal size={20} className="text-cyan-400" />
            Live Task Queue & Multi-Agent Execution Feed
          </h2>
          <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', marginTop: '4px' }}>
            Real-time feed of task execution, model routing, sandbox tests, and generated git diffs
          </p>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{ position: 'relative' }}>
            <Search size={16} style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }} />
            <input 
              type="text" 
              placeholder="Search issue or task ID..." 
              value={searchTerm} 
              onChange={e => setSearchTerm(e.target.value)}
              style={{
                background: 'rgba(255, 255, 255, 0.05)',
                border: '1px solid var(--border-color)',
                borderRadius: '8px',
                padding: '8px 12px 8px 36px',
                color: 'var(--text-main)',
                fontSize: '0.85rem',
                outline: 'none',
                width: '220px',
              }}
            />
          </div>

          <div className="glass-pill" style={{ display: 'flex', gap: '4px', padding: '4px' }}>
            <button 
              onClick={() => setStatusFilter('all')}
              style={{ background: statusFilter === 'all' ? 'rgba(99, 102, 241, 0.3)' : 'transparent', border: 'none', color: '#fff', padding: '4px 10px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.75rem' }}
            >All</button>
            <button 
              onClick={() => setStatusFilter('passed')}
              style={{ background: statusFilter === 'passed' ? 'rgba(16, 185, 129, 0.3)' : 'transparent', border: 'none', color: '#fff', padding: '4px 10px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.75rem' }}
            >Passed</button>
            <button 
              onClick={() => setStatusFilter('failed')}
              style={{ background: statusFilter === 'failed' ? 'rgba(244, 63, 94, 0.3)' : 'transparent', border: 'none', color: '#fff', padding: '4px 10px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.75rem' }}
            >Failed</button>
          </div>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        {filteredItems.map(item => {
          const isExpanded = expandedId === item.id;
          return (
            <div 
              key={item.id} 
              style={{
                background: 'rgba(255, 255, 255, 0.02)',
                border: '1px solid var(--border-color)',
                borderRadius: '12px',
                overflow: 'hidden',
                transition: 'border-color 0.2s ease',
              }}
            >
              <div 
                onClick={() => setExpandedId(isExpanded ? null : item.id)}
                style={{
                  padding: '16px 20px',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  userSelect: 'none',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flex: 1, minWidth: 0 }}>
                  {isExpanded ? <ChevronDown size={18} className="text-muted" /> : <ChevronRight size={18} className="text-muted" />}
                  
                  {item.success ? (
                    <span className="glass-pill badge-emerald" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <CheckCircle size={14} /> Passed
                    </span>
                  ) : (
                    <span className="glass-pill badge-rose" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <AlertTriangle size={14} /> Failed
                    </span>
                  )}

                  <span style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-main)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {item.issue}
                  </span>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '16px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                  <span className="glass-pill badge-indigo">{item.modelTier || 'CHEAP'}</span>
                  <span>{item.durationSeconds}s</span>
                  <span>{item.cost}</span>
                </div>
              </div>

              {isExpanded && (
                <div style={{ padding: '0 20px 20px 20px', borderTop: '1px solid rgba(255, 255, 255, 0.05)', background: 'rgba(0, 0, 0, 0.2)' }}>
                  {/* Traces / Spans */}
                  <div style={{ marginTop: '16px', marginBottom: '16px' }}>
                    <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '8px' }}>
                      Subagent Execution Trace Timeline
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                      {(item.spans || []).map((span, sIdx) => (
                        <div key={sIdx} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', background: 'rgba(255, 255, 255, 0.03)', padding: '6px 12px', borderRadius: '6px', fontSize: '0.8rem' }}>
                          <span style={{ color: 'var(--text-main)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#6366f1' }}></span>
                            {span.name}
                          </span>
                          <span style={{ color: 'var(--text-muted)' }}>{span.duration}s</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Patch View */}
                  {item.patch && (
                    <div>
                      <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-muted)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <GitCommit size={14} className="text-emerald-400" />
                        Generated Git Diff Patch
                      </div>
                      <pre style={{
                        background: '#040711',
                        border: '1px solid rgba(255, 255, 255, 0.1)',
                        borderRadius: '8px',
                        padding: '12px',
                        fontSize: '0.8rem',
                        overflowX: 'auto',
                        color: '#e2e8f0',
                        lineHeight: 1.5,
                      }}>
                        {item.patch.split('\n').map((line, lIdx) => {
                          let bg = 'transparent';
                          let color = '#94a3b8';
                          if (line.startsWith('+') && !line.startsWith('+++')) {
                            bg = 'rgba(16, 185, 129, 0.15)';
                            color = '#34d399';
                          } else if (line.startsWith('-') && !line.startsWith('---')) {
                            bg = 'rgba(244, 63, 94, 0.15)';
                            color = '#f87171';
                          }
                          return (
                            <div key={lIdx} style={{ background: bg, color: color, padding: '1px 4px', borderRadius: '2px' }}>
                              {line}
                            </div>
                          );
                        })}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
