"use client";

import { useState, useEffect } from "react";
import { format } from "date-fns";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip, ResponsiveContainer, Legend } from "recharts";
import { ScoreGroup } from "@/components/ScoreCircle";

export default function HistoryPage() {
    const [runs, setRuns] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

    useEffect(() => {
        const fetchRuns = async () => {
            try {
                const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/runs?limit=50`);
                if (res.ok) {
                    const data = await res.json();
                    setRuns(data);
                }
            } catch (err) {
                console.error("Failed to fetch runs", err);
            } finally {
                setLoading(false);
            }
        };
        fetchRuns();
    }, []);

    const selectedRun = runs.find(r => r.run_id === selectedRunId) || runs.find(r => r.id === selectedRunId);

    return (
        <div className="flex h-[calc(100vh-128px)] -m-xxl overflow-hidden">
            {/* History List Area */}
            <section className="flex-1 flex flex-col min-w-0 bg-background border-r border-outline-variant">
                {/* Page Header with Filters */}
                <div className="p-xl space-y-lg border-b border-outline-variant bg-surface-container-lowest">
                    <div className="flex justify-between items-end">
                        <div>
                            <p className="font-label-md text-label-md text-primary font-bold tracking-wider mb-xs">CONTINUOUS INTELLIGENCE</p>
                            <h2 className="font-headline-lg text-headline-lg text-on-surface">Intelligence History</h2>
                        </div>
                        <div className="flex items-center gap-sm">
                            <button className="flex items-center gap-xs px-md py-sm border border-outline-variant rounded-lg font-body-md text-body-md bg-surface-container-lowest text-outline cursor-not-allowed" disabled>
                                <span className="material-symbols-outlined text-[20px]">calendar_today</span>
                                Date Range
                            </button>
                            <button className="flex items-center gap-xs px-md py-sm border border-outline-variant rounded-lg font-body-md text-body-md bg-surface-container-lowest text-outline cursor-not-allowed" disabled>
                                <span className="material-symbols-outlined text-[20px]">filter_list</span>
                                More Filters
                            </button>
                        </div>
                    </div>
                </div>

                {/* Timeline List */}
                <div className="flex-1 overflow-y-auto p-xl space-y-md custom-scrollbar">
                    {loading ? (
                        <div className="text-center py-12 text-on-surface-variant">Loading history...</div>
                    ) : runs.length === 0 ? (
                        <div className="text-center py-12 text-on-surface-variant">No optimizations recorded.</div>
                    ) : (
                        runs.map((run, i) => {
                            const sum = run.run_summary || {};
                            const roi = sum.roi || {};
                            const isSelected = (run.run_id || run.id) === selectedRunId;
                            
                            const isDeployed = run.deploy_status === "deployed" || run.deploy_status === "deployed_supervised";
                            const isFailed = run.deploy_status === "failed" || run.deploy_status === "failed_gates" || run.status === "failed";
                            
                            return (
                                <div 
                                    key={run.run_id || run.id || i}
                                    onClick={() => setSelectedRunId(run.run_id || run.id)}
                                    className={`group relative bg-surface-container-lowest border ${isSelected ? 'border-primary shadow-md' : 'border-outline-variant'} rounded-xl p-lg cursor-pointer hover:border-primary hover:shadow-sm transition-all`}
                                >
                                    <div className={`absolute left-0 top-1/2 -translate-y-1/2 w-1 h-12 bg-primary rounded-r-full transition-opacity ${isSelected ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'}`}></div>
                                    <div className="flex justify-between items-start mb-md">
                                        <div className="space-y-xs">
                                            <div className="flex items-center gap-sm text-on-surface-variant font-label-md text-label-md">
                                                <span className="material-symbols-outlined text-[16px]">schedule</span>
                                                {run.start_time ? format(new Date(run.start_time), "MMM d, HH:mm") : "-"}
                                                <span className="w-1 h-1 bg-outline-variant rounded-full"></span>
                                                <span>ID: {(run.run_id || run.id)?.substring(0,8)}</span>
                                            </div>
                                            <h3 className="font-headline-sm text-headline-sm text-on-surface group-hover:text-primary transition-colors">
                                                {sum.target_page || "Optimization Workflow"}
                                            </h3>
                                        </div>
                                        <span className={`px-md py-xs rounded-full font-label-md text-label-md font-bold ${
                                            isDeployed ? 'bg-tertiary-container text-on-tertiary-container' : 
                                            isFailed ? 'bg-error-container text-on-error-container' : 
                                            'bg-surface-variant text-on-surface-variant'
                                        }`}>
                                            {run.deploy_status || run.status || "UNKNOWN"}
                                        </span>
                                    </div>
                                    <div className="grid grid-cols-1 md:grid-cols-3 gap-xl">
                                        <div className="p-md bg-surface-container-low rounded-lg border border-outline-variant/50">
                                            <p className="font-label-md text-label-md text-on-surface-variant mb-xs uppercase font-bold opacity-60">Impact Outcome</p>
                                            <div className="flex items-end gap-xs">
                                                <span className={`font-headline-md text-headline-md ${roi.score_delta > 0 ? 'text-tertiary' : 'text-on-surface'}`}>
                                                    {roi.score_delta > 0 ? '+' : ''}{roi.score_delta?.toFixed(1) || '0'}
                                                </span>
                                                <span className="font-body-md text-body-md text-on-surface-variant pb-xs">Points</span>
                                            </div>
                                        </div>
                                        <div className="p-md bg-surface-container-low rounded-lg border border-outline-variant/50">
                                            <p className="font-label-md text-label-md text-on-surface-variant mb-xs uppercase font-bold opacity-60">Primary Metric</p>
                                            <div className="flex items-center gap-sm">
                                                <span className="font-body-md text-body-md font-bold text-on-surface">{sum.target_metric || "Core Web Vitals"}</span>
                                            </div>
                                        </div>
                                        <div className="p-md bg-surface-container-low rounded-lg border border-outline-variant/50">
                                            <p className="font-label-md text-label-md text-on-surface-variant mb-xs uppercase font-bold opacity-60">Revenue Lift</p>
                                            <div className="flex items-center gap-sm">
                                                <span className="material-symbols-outlined text-primary">trending_up</span>
                                                <span className="font-body-md text-body-md">+{roi.estimated_conversion_lift_pct?.toFixed(1) || '0.0'}%</span>
                                            </div>
                                        </div>
                                    </div>
                                </div>
                            );
                        })
                    )}
                </div>
            </section>

            {/* Detail Panel */}
            <aside className={`w-[450px] shrink-0 flex flex-col ${selectedRun ? 'bg-surface-container-lowest border-l border-outline-variant' : 'bg-surface-container-low items-center justify-center p-xxl text-center'} overflow-y-auto custom-scrollbar`}>
                {!selectedRun ? (
                    <>
                        <div className="relative w-48 h-48 mb-xl">
                            <div className="absolute inset-0 bg-primary/5 rounded-full animate-pulse"></div>
                            <div className="absolute inset-8 border-2 border-dashed border-outline-variant rounded-full"></div>
                            <div className="absolute inset-0 flex items-center justify-center">
                                <span className="material-symbols-outlined text-[64px] text-outline opacity-40">find_in_page</span>
                            </div>
                        </div>
                        <h4 className="font-headline-sm text-headline-sm text-on-surface mb-md">No Cycle Selected</h4>
                        <p className="font-body-md text-body-md text-on-surface-variant max-w-sm mb-xl">
                            Select an optimization cycle from the history timeline to view detailed root cause analysis, deployment logs, and safety validation reports.
                        </p>
                    </>
                ) : (
                    <div className="w-full h-full p-xl flex flex-col animate-fade-slide-up">
                        <div className="flex items-center justify-between mb-xl">
                            <h3 className="font-headline-md text-headline-md">Optimization Details</h3>
                            <div className="flex items-center gap-md">
                                <a 
                                    href={`/live?run_id=${selectedRun.run_id || selectedRun.id}`}
                                    className="px-md py-sm bg-primary text-on-primary rounded-lg font-label-md hover:opacity-90 transition-opacity"
                                >
                                    Live View
                                </a>
                                <button
                                    onClick={() => {
                                        const blob = new Blob([JSON.stringify(selectedRun, null, 2)], { type: "application/json" });
                                        const url = URL.createObjectURL(blob);
                                        const a = document.createElement("a");
                                        a.href = url;
                                        a.download = `awpis_run_${selectedRun.run_id || selectedRun.id}.json`;
                                        a.click();
                                        URL.revokeObjectURL(url);
                                    }}
                                    className="px-md py-sm border border-outline text-on-surface rounded-lg font-label-md hover:bg-surface-container-high transition-colors flex items-center gap-xs"
                                >
                                    <span className="material-symbols-outlined text-[18px]">download</span>
                                    Download JSON
                                </button>
                                <button className="p-xs hover:bg-surface-container-high rounded-full" onClick={() => setSelectedRunId(null)}>
                                    <span className="material-symbols-outlined">close</span>
                                </button>
                            </div>
                        </div>
                        
                        <div className="space-y-xl flex-grow">
                            {/* Analysis Summary */}
                            <div className="p-lg bg-surface-container-lowest border border-outline-variant rounded-xl shadow-sm">
                                <h4 className="font-label-md text-label-md font-bold text-primary uppercase mb-md flex items-center gap-2">
                                    <span className="material-symbols-outlined text-sm">psychology</span>
                                    AI Orchestrator Note
                                </h4>
                                <p className="font-body-md text-body-md text-on-surface-variant leading-relaxed">
                                    {selectedRun.run_summary?.roi?.message || "Optimization executed autonomously. Fixes applied to target metrics successfully."}
                                </p>
                            </div>

                            {/* Chart */}
                            {selectedRun.run_summary?.roi?.scores_before && selectedRun.run_summary?.roi?.scores_after && (
                                <div className="space-y-md">
                                    <h4 className="font-label-md text-label-md font-bold text-on-surface-variant uppercase">Performance Impact</h4>
                                    <div className="flex justify-between items-center bg-surface-container-low p-md rounded-xl border border-outline-variant shadow-sm">
                                        <div className="flex-1">
                                            <div className="text-[10px] text-on-surface-variant mb-2 font-bold uppercase tracking-widest">Baseline</div>
                                            <ScoreGroup scores={selectedRun.run_summary.roi.scores_before} />
                                        </div>
                                        <span className="material-symbols-outlined text-outline mx-md">arrow_right_alt</span>
                                        <div className="flex-1">
                                            <div className="text-[10px] text-primary mb-2 font-bold uppercase tracking-widest">Optimized</div>
                                            <ScoreGroup scores={selectedRun.run_summary.roi.scores_after} />
                                        </div>
                                    </div>
                                    
                                    <div className="h-[200px] w-full bg-surface-container-lowest p-md rounded-xl border border-outline-variant shadow-sm">
                                        <ResponsiveContainer width="100%" height="100%" minWidth={1} minHeight={1}>
                                            <BarChart 
                                                data={[{
                                                    name: 'Score',
                                                    Before: selectedRun.run_summary.roi.score_before || 0,
                                                    After: selectedRun.run_summary.roi.score_after || 0,
                                                }]} 
                                                margin={{ top: 20, right: 30, left: 0, bottom: 5 }}
                                            >
                                                <CartesianGrid strokeDasharray="3 3" stroke="#e1e2e4" vertical={false} />
                                                <XAxis dataKey="name" stroke="#737685" tick={{fill: '#737685', fontSize: 12}} />
                                                <YAxis domain={[0, 100]} stroke="#737685" tick={{fill: '#737685', fontSize: 12}} />
                                                <RechartsTooltip 
                                                    cursor={{fill: '#f3f4f6'}} 
                                                    contentStyle={{ backgroundColor: '#ffffff', borderColor: '#e1e2e4', borderRadius: '8px', padding: '12px', fontSize: '12px', fontWeight: 500, color: '#191c1e' }}
                                                />
                                                <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
                                                <Bar dataKey="Before" fill="#4c5e85" radius={[4, 4, 0, 0]} />
                                                <Bar dataKey="After" fill="#003d9b" radius={[4, 4, 0, 0]} />
                                            </BarChart>
                                        </ResponsiveContainer>
                                    </div>
                                </div>
                            )}

                            {/* Timeline Logs */}
                            <div className="space-y-md">
                                <h4 className="font-label-md text-label-md font-bold text-on-surface-variant uppercase">Execution Timeline</h4>
                                <div className="space-y-sm bg-surface-container-low p-md rounded-lg border border-outline-variant h-[250px] overflow-y-auto custom-scrollbar">
                                    {selectedRun.run_summary?.agent_steps && selectedRun.run_summary.agent_steps.length > 0 ? (
                                        selectedRun.run_summary.agent_steps.map((step: any, idx: number) => (
                                            <div key={idx} className="flex items-start gap-md p-xs border-b border-outline-variant/30 last:border-0">
                                                <span className="material-symbols-outlined text-tertiary text-[18px] mt-0.5" style={{fontVariationSettings: "'FILL' 1"}}>check_circle</span>
                                                <div className="flex-1 flex flex-col">
                                                    <span className="font-mono-label text-on-surface-variant text-xs font-bold uppercase">{step.agent.replace('_', ' ')}</span>
                                                    <span className="font-body-md text-on-surface text-sm">{step.summary}</span>
                                                </div>
                                                <span className="text-[10px] text-on-surface-variant bg-surface-container px-2 py-0.5 rounded">{step.duration_ms}ms</span>
                                            </div>
                                        ))
                                    ) : (
                                        <div className="text-sm text-on-surface-variant text-center py-8">Timeline not available for this run.</div>
                                    )}
                                </div>
                            </div>
                        </div>
                    </div>
                )}
            </aside>
        </div>
    );
}
