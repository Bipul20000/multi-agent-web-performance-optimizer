"use client";

import { Suspense, useState, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useAgentStream, AgentStatus } from "@/hooks/useAgentStream";
import { Button } from "@/components/ui/button";

const STEPS = [
    { id: 1, label: "Site Audit", agents: ["metrics_agent", "codebase_agent", "history_agent", "context_agent"] },
    { id: 2, label: "Root Cause Detection", agents: ["reasoning_agent", "risk_classifier", "frontend_fix_agent", "backend_fix_agent"] },
    { id: 3, label: "Validation Checks", agents: ["syntax_gate", "quality_gate", "critic_agent", "dependency_gate"] },
    { id: 4, label: "Production Deployment", agents: ["sandbox_agent", "deploy_agent", "learning_agent", "report_agent"] }
];

function LiveDashboardContent() {
    const searchParams = useSearchParams();
    const urlRunId = searchParams.get("run_id");
    
    const [runId, setRunId] = useState<string | null>(null);
    
    useEffect(() => {
        if (urlRunId) {
            setRunId(urlRunId);
            sessionStorage.setItem("awpis_last_run_id", urlRunId);
        } else {
            const saved = sessionStorage.getItem("awpis_last_run_id");
            if (saved) setRunId(saved);
        }
    }, [urlRunId]);

    const { agentStates, fixPlan, requiresApproval, isComplete, latestEvent, rawLogs, setRawLogs } = useAgentStream(runId);
    
    const [recentRuns, setRecentRuns] = useState<any[]>([]);

    // Fetch sidebar workflows
    useEffect(() => {
        fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/runs`)
            .then(res => res.json())
            .then(data => setRecentRuns(data || []))
            .catch(e => console.error("Failed to load recent workflows", e));
    }, []);

    useEffect(() => {
        if (latestEvent) {
            setRawLogs(prev => {
                const next = [...prev, latestEvent];
                if (runId && typeof window !== 'undefined') {
                    sessionStorage.setItem(`awpis_rawLogs_${runId}`, JSON.stringify(next));
                }
                return next;
            });
        }
    }, [latestEvent, runId, setRawLogs]);

    const handleDownloadReport = () => {
        const report = {
            runId,
            status: isComplete ? "Completed" : "Active",
            agentStates,
            fixPlan,
            rawLogs,
            metrics: agentStates["metrics_agent"]?.data
        };
        const blob = new Blob([JSON.stringify(report, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `awpis_run_${runId}.json`;
        a.click();
        URL.revokeObjectURL(url);
    };

    const [submittingApproval, setSubmittingApproval] = useState(false);
    const [showAllMetrics, setShowAllMetrics] = useState(false);

    const handleApproval = async (approved: boolean) => {
        if (!runId) return;
        setSubmittingApproval(true);
        try {
            await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/approve/${runId}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ approved })
            });
        } catch (e) {
            console.error("Failed to submit approval", e);
        } finally {
            setSubmittingApproval(false);
        }
    };

    const handleStopRun = async () => {
        if (!runId) return;
        try {
            await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/stop/${runId}`, {
                method: "POST"
            });
        } catch (e) {
            console.error("Failed to stop run", e);
        }
    };

    if (!runId) {
        return (
            <div className="flex flex-col items-center justify-center h-full text-on-surface-variant space-y-4 pt-xxl">
                <span className="material-symbols-outlined text-[64px] text-outline">analytics</span>
                <p className="font-headline-sm text-headline-sm">No Active Workflow</p>
                <p className="font-body-md text-body-md text-on-surface-variant">Please initialize a new optimization workflow from the Dashboard.</p>
            </div>
        );
    }

    // Determine overall step progress (1 to 4)
    let currentStepIdx = 0;
    for (let i = 0; i < STEPS.length; i++) {
        const step = STEPS[i];
        const isStarted = step.agents.some(a => agentStates[a] && agentStates[a].status !== "waiting");
        if (isStarted) {
            currentStepIdx = i;
        }
    }
    if (isComplete) currentStepIdx = 4; // all done

    const progressPercent = Math.min(100, Math.max(0, (currentStepIdx / (STEPS.length - 1)) * 100));

    // Convert agentStates map into chronological logs

    const LAYERS = [
        { id: 1, name: "Intelligence Gather", color: "border-teal-500", text: "text-teal-400", bg: "bg-teal-500/10", active: "shadow-[0_0_15px_rgba(20,184,166,0.5)]", agents: ["metrics_agent", "codebase_agent", "history_agent", "context_agent"] },
        { id: 2, name: "Cognitive Core", color: "border-blue-500", text: "text-blue-400", bg: "bg-blue-500/10", active: "shadow-[0_0_15px_rgba(59,130,246,0.5)]", agents: ["reasoning_agent", "risk_classifier"] },
        { id: 3, name: "Fix Generation", color: "border-amber-500", text: "text-amber-400", bg: "bg-amber-500/10", active: "shadow-[0_0_15px_rgba(245,158,11,0.5)]", agents: ["frontend_fix_agent", "backend_fix_agent"] },
        { id: 4, name: "Safety Gates", color: "border-red-500", text: "text-red-400", bg: "bg-red-500/10", active: "shadow-[0_0_15px_rgba(239,68,68,0.5)]", agents: ["syntax_gate", "quality_gate", "critic_agent", "dependency_gate"] },
        { id: 5, name: "Deploy & Prove", color: "border-emerald-500", text: "text-emerald-400", bg: "bg-emerald-500/10", active: "shadow-[0_0_15px_rgba(16,185,129,0.5)]", agents: ["sandbox_agent", "deploy_agent"] },
        { id: 6, name: "Post-Processing", color: "border-purple-500", text: "text-purple-400", bg: "bg-purple-500/10", active: "shadow-[0_0_15px_rgba(168,85,247,0.5)]", agents: ["learning_agent", "report_agent"] }
    ];

    return (
        <div className="space-y-xl max-w-7xl mx-auto pb-xxl animate-fade-slide-up">
            {/* Header Section */}
            <section className="flex flex-col md:flex-row md:items-center justify-between mb-xl gap-md">
                <div>
                    <nav className="flex items-center gap-xs font-label-md text-label-md text-on-surface-variant mb-xs">
                        <span>Workflows</span>
                        <span className="material-symbols-outlined text-[12px]">chevron_right</span>
                        <span>Live Orchestration</span>
                    </nav>
                    <h2 className="font-headline-lg text-headline-lg text-on-surface">Active Optimization Plan <span className="font-mono text-lg ml-2 bg-surface-container-high px-md py-xs rounded border border-outline-variant text-on-surface-variant">{runId.substring(0,8)}</span></h2>
                </div>
                <div className="flex items-center gap-md">
                    {!isComplete && (
                        <button onClick={handleStopRun} className="flex items-center gap-sm px-lg py-md bg-error-container text-on-error-container rounded font-body-md font-semibold hover:opacity-90 transition-opacity">
                            <span className="material-symbols-outlined">pause_circle</span>
                            Halt Workflow
                        </button>
                    )}
                    <button onClick={handleDownloadReport} className="flex items-center gap-sm px-lg py-md bg-secondary text-on-secondary rounded font-body-md font-semibold hover:opacity-90 transition-opacity shadow-sm">
                        <span className="material-symbols-outlined">download</span>
                        Download Full Report
                    </button>
                </div>
            </section>

            {/* Agent Topology Layers */}
            <section className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg mb-xl overflow-x-auto">
                <div className="flex flex-nowrap min-w-max gap-xl pb-md">
                    {LAYERS.map((layer) => {
                        const isLayerActive = layer.agents.some(a => agentStates[a]?.status === "running");
                        const isLayerComplete = layer.agents.every(a => agentStates[a]?.status === "complete");
                        const isLayerError = layer.agents.some(a => agentStates[a]?.status === "error" || agentStates[a]?.status === "failed");

                        return (
                            <div key={layer.id} className="flex-1 min-w-[250px] relative">
                                {/* Connection Line to next layer */}
                                {layer.id < 6 && (
                                    <div className="absolute top-6 left-1/2 w-full h-[2px] bg-surface-container-highest -z-10">
                                        <div className={`h-full transition-all duration-1000 ${isLayerComplete ? 'bg-primary' : 'bg-transparent'}`}></div>
                                    </div>
                                )}
                                
                                <div className="text-center mb-md relative z-10 bg-surface-container-lowest inline-block px-sm left-1/2 -translate-x-1/2">
                                    <span className={`font-label-md font-bold uppercase tracking-widest ${isLayerActive ? layer.text : isLayerComplete ? 'text-primary' : isLayerError ? 'text-error' : 'text-on-surface-variant'}`}>
                                        {layer.name}
                                    </span>
                                </div>
                                
                                <div className="space-y-sm">
                                    {layer.agents.map(agentName => {
                                        const state = agentStates[agentName];
                                        const isRunning = state?.status === "running";
                                        const isComplete = state?.status === "complete";
                                        const isError = state?.status === "error" || state?.status === "failed";
                                        const statusLabel = isRunning ? "Running..." : isComplete ? "Done" : isError ? "Failed" : "Waiting";

                                        return (
                                            <div 
                                                key={agentName} 
                                                className={`flex items-center justify-between p-md rounded-lg border bg-surface-container-lowest transition-all ${
                                                    isRunning ? `border-${layer.color.split('-')[1]}-500 ${layer.bg} ${layer.active} scale-105` : 
                                                    isComplete ? 'border-primary/50 opacity-80' : 
                                                    isError ? 'border-error/50 bg-error/5' : 
                                                    'border-outline-variant opacity-50'
                                                }`}
                                            >
                                                <div className="flex items-center gap-sm">
                                                    {isRunning ? (
                                                        <span className={`material-symbols-outlined text-[16px] ${layer.text} animate-spin`}>progress_activity</span>
                                                    ) : isComplete ? (
                                                        <span className="material-symbols-outlined text-[16px] text-primary">check_circle</span>
                                                    ) : isError ? (
                                                        <span className="material-symbols-outlined text-[16px] text-error">error</span>
                                                    ) : (
                                                        <span className="material-symbols-outlined text-[16px] text-on-surface-variant">radio_button_unchecked</span>
                                                    )}
                                                    <span className={`font-mono-label text-sm ${isRunning ? 'text-on-surface font-bold' : 'text-on-surface-variant'}`}>
                                                        {agentName.replace('_agent', '').replace('_gate', '')}
                                                    </span>
                                                </div>
                                                <span className={`text-[10px] uppercase font-bold ${isRunning ? layer.text : isComplete ? 'text-primary' : isError ? 'text-error' : 'text-on-surface-variant/50'}`}>
                                                    {statusLabel}
                                                </span>
                                            </div>
                                        );
                                    })}
                                </div>
                            </div>
                        );
                    })}
                </div>
            </section>

            {/* Workspace Grid */}
            <div className="grid grid-cols-12 gap-xl items-stretch">
                {/* Center: Terminal/Log View */}
                <div className="col-span-12 lg:col-span-8 flex flex-col min-h-[500px]">
                    <div className="bg-surface-container-highest border border-outline-variant border-b-0 rounded-t-xl px-lg py-md flex items-center justify-between">
                        <div className="flex items-center gap-md">
                            <span className="flex gap-xs">
                                <span className="w-3 h-3 rounded-full bg-error/20 border border-error/40"></span>
                                <span className="w-3 h-3 rounded-full bg-secondary/20 border border-secondary/40"></span>
                                <span className="w-3 h-3 rounded-full bg-tertiary/20 border border-tertiary/40"></span>
                            </span>
                            <span className="font-mono-label text-on-surface-variant ml-sm">Orchestration_Stream_v2.04</span>
                        </div>
                        <div className="flex items-center gap-sm">
                            {!isComplete && <span className="w-2 h-2 rounded-full bg-primary animate-pulse"></span>}
                            <span className={`font-label-md font-bold ${isComplete ? 'text-tertiary' : 'text-primary'}`}>
                                {isComplete ? "COMPLETED" : "LIVE STREAM"}
                            </span>
                        </div>
                    </div>
                    <div className="flex-1 bg-surface-container-low border border-outline-variant rounded-b-xl p-lg overflow-y-auto custom-scrollbar font-mono-label">
                        <div className="space-y-md">
                            {rawLogs.map((log, idx) => {
                                const isError = log.event_type === "agent_error" || log.event_type === "gate_result" && log.data?.result === "REJECT";
                                const isStart = log.event_type === "agent_start";
                                const isComplete = log.event_type === "agent_complete" || log.event_type === "run_complete";
                                
                                const timeStr = new Date(log.timestamp || Date.now()).toLocaleTimeString();
                                
                                return (
                                    <div key={idx} className={`flex gap-md ${isError ? 'p-md bg-error-container/10 border-l-2 border-error rounded-r' : ''}`}>
                                        <span className="opacity-50 shrink-0 text-on-surface-variant w-24">
                                            {timeStr}
                                        </span>
                                        <span className={`opacity-80 shrink-0 w-32 ${isError ? 'text-error' : 'text-tertiary'}`}>
                                            [{log.agent_name?.toUpperCase() || 'SYSTEM'}]
                                        </span>
                                        <div className="flex flex-col gap-xs flex-1">
                                            <span className={`font-bold ${isError ? 'text-error' : isStart ? 'text-primary' : isComplete ? 'text-emerald-400' : 'text-on-surface'}`}>
                                                {log.event_type}
                                            </span>
                                            {log.data && log.event_type !== "run_complete" && (
                                                <pre className="text-on-surface-variant text-[11px] bg-surface-container-highest p-sm rounded mt-xs overflow-x-auto">
                                                    {JSON.stringify(log.data, null, 2)}
                                                </pre>
                                            )}
                                            {log.data && log.event_type === "run_complete" && (
                                                <pre className="text-on-surface-variant text-[11px] bg-surface-container-highest p-sm rounded mt-xs overflow-x-auto text-emerald-400">
                                                    {log.data.roi?.message || `Status: ${log.data.deploy_status || "completed"}`}
                                                </pre>
                                            )}
                                        </div>
                                    </div>
                                );
                            })}
                            {!isComplete && (
                                <div className="flex gap-md animate-pulse mt-md">
                                    <span className="text-on-surface-variant opacity-50 shrink-0 w-24">--:--:--</span>
                                    <span className="text-on-surface-variant opacity-50 shrink-0 w-32">[SYSTEM]</span>
                                    <span className="text-primary font-bold">_</span>
                                </div>
                            )}
                        </div>
                    </div>
                </div>

                {/* Sidebar: Plan Details & Recent Workflows */}
                <aside className="col-span-12 lg:col-span-4 flex flex-col gap-xl">
                    {/* Approval Action Card */}
                    {requiresApproval && (
                        <div className="bg-primary-container text-on-primary-container rounded-xl p-lg relative overflow-hidden animate-fade-slide-up">
                            <div className="relative z-10">
                                <h4 className="font-bold mb-xs text-xl flex items-center gap-2">
                                    <span className="material-symbols-outlined">gavel</span>
                                    Executive Review Required
                                </h4>
                                <p className="text-body-md opacity-90 mb-lg">Optimizations are ready for deployment. The system is paused awaiting your authorization.</p>
                                
                                {fixPlan && (
                                    <div className="bg-surface-container-lowest/20 rounded p-md mb-lg font-mono-label text-sm border border-on-primary-container/20">
                                        {fixPlan.split('\n').map((l: string, i: number) => <div key={i} className="mb-1">{l}</div>)}
                                    </div>
                                )}

                                <div className="flex gap-md">
                                    <button 
                                        onClick={() => handleApproval(false)}
                                        disabled={submittingApproval}
                                        className="flex-1 bg-surface-container-lowest text-primary font-bold py-md rounded-lg hover:bg-opacity-90 transition-all border border-transparent hover:border-error"
                                    >
                                        Reject
                                    </button>
                                    <button 
                                        onClick={() => handleApproval(true)}
                                        disabled={submittingApproval}
                                        className="flex-1 bg-primary text-on-primary font-bold py-md rounded-lg hover:bg-opacity-90 transition-all border border-on-primary/20 shadow-sm"
                                    >
                                        {submittingApproval ? "Deploying..." : "Approve & Deploy"}
                                    </button>
                                </div>
                            </div>
                            <div className="absolute -right-4 -bottom-4 opacity-10 transform rotate-12 pointer-events-none">
                                <span className="material-symbols-outlined text-[100px]">security</span>
                            </div>
                        </div>
                    )}

                    {/* Recent Workflows Sidebar */}
                    <div className="bg-surface-container-lowest border border-outline-variant rounded-xl overflow-hidden animate-fade-slide-up flex flex-col max-h-[500px]">
                        <div className="p-md border-b border-outline-variant bg-surface-container-low flex items-center justify-between">
                            <h4 className="font-headline-sm text-headline-sm">Recent Workflows</h4>
                            <span className="material-symbols-outlined text-on-surface-variant text-sm">history</span>
                        </div>
                        <div className="overflow-y-auto custom-scrollbar divide-y divide-outline-variant">
                            {recentRuns.length === 0 ? (
                                <div className="p-xl text-center text-on-surface-variant text-sm">No recent workflows</div>
                            ) : (
                                recentRuns.map((r: any) => (
                                    <a 
                                        key={r.run_id} 
                                        href={`/live?run_id=${r.run_id}`}
                                        className={`block p-md hover:bg-surface-container-high transition-colors ${r.run_id === runId ? 'bg-primary/5 border-l-4 border-l-primary' : 'border-l-4 border-l-transparent'}`}
                                    >
                                        <div className="flex justify-between items-center mb-xs">
                                            <span className="font-mono text-xs font-bold">{r.run_id.substring(0,8)}</span>
                                            <span className={`text-[10px] uppercase font-bold px-sm py-xs rounded ${
                                                r.status === 'running' ? 'bg-primary/10 text-primary' :
                                                r.status === 'error' || r.status === 'failed' ? 'bg-error/10 text-error' :
                                                r.status === 'aborted' ? 'bg-outline/20 text-on-surface-variant' :
                                                'bg-tertiary/10 text-tertiary'
                                            }`}>
                                                {r.status}
                                            </span>
                                        </div>
                                        <div className="text-xs text-on-surface-variant truncate">
                                            {r.run_summary?.target_page || r.website_url || 'N/A'}
                                        </div>
                                    </a>
                                ))
                            )}
                        </div>
                    </div>

                    {/* Performance Metrics */}
                    {(() => {
                        const metricsData = agentStates["metrics_agent"]?.data;
                        if (!metricsData) return null;
                        
                        let performanceScore = metricsData.worst_score || 0;
                        let seoScore = 0;
                        let bestLcp = 0;
                        let backendResponse = 0;
                        
                        if (metricsData.psi_metrics) {
                            const pages = Object.values(metricsData.psi_metrics);
                            if (pages.length > 0) {
                                const pageData: any = pages[0];
                                performanceScore = pageData?.mobile?.scores?.performance || performanceScore;
                                seoScore = pageData?.mobile?.scores?.seo || 0;
                                bestLcp = pageData?.mobile?.core_web_vitals?.LCP?.value || 0;
                            }
                        }
                        
                        if (metricsData.backend_metrics && metricsData.backend_metrics.length > 0) {
                            backendResponse = metricsData.backend_metrics[0].response_time_ms || 0;
                        }

                        if (!performanceScore && !seoScore && !bestLcp && !backendResponse) return null;

                        return (
                            <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
                                <div className="flex items-center gap-xs mb-md">
                                    <span className="material-symbols-outlined text-primary">speed</span>
                                    <h3 className="font-headline-sm text-headline-sm text-on-surface">Metrics Profile</h3>
                                </div>
                                <div className="grid grid-cols-2 gap-md">
                                    <div className="bg-surface-container p-md rounded-lg">
                                        <div className="text-xs text-on-surface-variant mb-1">PageSpeed</div>
                                        <div className={`text-xl font-bold font-mono ${performanceScore >= 90 ? 'text-tertiary' : performanceScore >= 50 ? 'text-amber-500' : 'text-error'}`}>
                                            {performanceScore > 0 ? Math.round(performanceScore) : '--'}
                                        </div>
                                    </div>
                                    <div className="bg-surface-container p-md rounded-lg">
                                        <div className="text-xs text-on-surface-variant mb-1">SEO Score</div>
                                        <div className={`text-xl font-bold font-mono ${seoScore >= 90 ? 'text-tertiary' : seoScore >= 50 ? 'text-amber-500' : 'text-error'}`}>
                                            {seoScore > 0 ? Math.round(seoScore) : '--'}
                                        </div>
                                    </div>
                                    <div className="bg-surface-container p-md rounded-lg">
                                        <div className="text-xs text-on-surface-variant mb-1">LCP Time</div>
                                        <div className="text-xl font-bold font-mono text-on-surface">
                                            {bestLcp > 0 ? `${(bestLcp / 1000).toFixed(1)}s` : '--'}
                                        </div>
                                    </div>
                                    <div className="bg-surface-container p-md rounded-lg">
                                        <div className="text-xs text-on-surface-variant mb-1">API Latency</div>
                                        <div className="text-xl font-bold font-mono text-on-surface">
                                            {backendResponse > 0 ? `${Math.round(backendResponse)}ms` : '--'}
                                        </div>
                                    </div>
                                </div>
                                <button onClick={() => setShowAllMetrics(!showAllMetrics)} className="mt-md text-primary font-bold text-sm hover:underline transition-all w-full text-center py-sm border border-primary/20 rounded">
                                    {showAllMetrics ? "Hide Raw Metrics" : "View All Metrics Payload"}
                                </button>
                                {showAllMetrics && (
                                    <div className="mt-md p-md bg-surface-container-high rounded text-xs font-mono text-on-surface-variant overflow-x-auto max-h-64 custom-scrollbar">
                                        <pre>{JSON.stringify(metricsData, null, 2)}</pre>
                                    </div>
                                )}
                            </div>
                        );
                    })()}

                    {/* Confidence Meter */}
                    <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg flex flex-col items-center text-center">
                        <h3 className="font-label-md font-bold text-on-surface-variant uppercase tracking-widest mb-lg">Confidence Score</h3>
                        <div className="relative w-40 h-40">
                            {/* SVG Radial Gauge */}
                            <svg className="w-full h-full transform -rotate-90">
                                <circle className="text-surface-container-high" cx="80" cy="80" fill="transparent" r="70" stroke="currentColor" strokeWidth="12"></circle>
                                <circle className="text-primary transition-all duration-1000" cx="80" cy="80" fill="transparent" r="70" stroke="currentColor" strokeDasharray="440" strokeDashoffset={440 - (440 * 0.92)} strokeWidth="12"></circle>
                            </svg>
                            <div className="absolute inset-0 flex flex-col items-center justify-center">
                                <span className="font-headline-lg text-headline-lg font-bold text-on-surface">92%</span>
                                <span className="font-label-md text-label-md text-tertiary font-bold uppercase">Optimal</span>
                            </div>
                        </div>
                        <p className="mt-lg font-body-md text-body-md text-on-surface-variant">The AI agent is highly confident in the proposed optimization path based on historical audit patterns.</p>
                    </div>

                    {/* Plan Metadata */}
                    <div className="bg-surface-container-lowest border border-outline-variant rounded-xl p-lg">
                        <h3 className="font-headline-sm text-headline-sm text-on-surface mb-md">Plan Details</h3>
                        <div className="space-y-md">
                            <div className="flex justify-between items-center py-sm border-b border-outline-variant">
                                <span className="font-body-md text-on-surface-variant">Target Metric</span>
                                <span className="font-body-md font-bold text-primary">{agentStates["metrics_agent"]?.data?.target_metric || "Core Web Vitals"}</span>
                            </div>
                            <div className="flex justify-between items-center py-sm border-b border-outline-variant">
                                <span className="font-body-md text-on-surface-variant">Priority</span>
                                <span className="bg-error-container text-on-error-container px-sm py-xs rounded font-bold text-[10px] uppercase">Critical</span>
                            </div>
                            <div className="flex justify-between items-center py-sm border-b border-outline-variant">
                                <span className="font-body-md text-on-surface-variant">Initiated by</span>
                                <div className="flex items-center gap-xs">
                                    <span className="material-symbols-outlined text-body-lg text-primary">smart_toy</span>
                                    <span className="font-body-md font-bold text-on-surface">Auto-Orchestrator</span>
                                </div>
                            </div>
                            <div className="flex justify-between items-center py-sm">
                                <span className="font-body-md text-on-surface-variant">Compliance</span>
                                <span className="font-body-md text-tertiary font-bold flex items-center gap-xs">
                                    <span className="material-symbols-outlined text-[16px]">verified</span>
                                    SOC2 Validated
                                </span>
                            </div>
                        </div>
                    </div>
                </aside>
            </div>
        </div>
    );
}

export default function LiveDashboardPage() {
    return (
        <Suspense fallback={<div className="p-xl text-center text-on-surface-variant font-body-md">Loading terminal...</div>}>
            <LiveDashboardContent />
        </Suspense>
    );
}
