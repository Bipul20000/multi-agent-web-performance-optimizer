"use client";

import { useState, useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import { format } from "date-fns";

export default function DashboardPage() {
    const router = useRouter();
    const [runs, setRuns] = useState<any[]>([]);
    const [loading, setLoading] = useState(true);
    const [isRunModalOpen, setIsRunModalOpen] = useState(false);
    
    // Modal state
    const [url, setUrl] = useState("https://example.com");
    const [mode, setMode] = useState<"AUTOMATED" | "SUPERVISED">("SUPERVISED");
    const [isSubmitting, setIsSubmitting] = useState(false);

    useEffect(() => {
        const fetchRuns = async () => {
            try {
                const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/runs`);
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

    const startRun = async () => {
        setIsSubmitting(true);
        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/run`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ website_url: url, run_mode: mode })
            });
            
            if (res.ok) {
                const data = await res.json();
                setIsRunModalOpen(false);
                router.push(`/live?run_id=${data.run_id}`);
            } else {
                console.error("Run failed to start");
            }
        } catch (err) {
            console.error("Run request failed", err);
        } finally {
            setIsSubmitting(false);
        }
    };

    const completedRuns = runs.filter(r => r.status === "complete");
    const lastRun = completedRuns[0];
    const lastScore = lastRun?.final_score || 0;
    const totalFixes = completedRuns.filter(r => ["deployed", "deployed_supervised"].includes(r.deploy_status)).length;
    const lastDelta = lastRun?.run_summary?.roi?.score_delta || 0;
    const conversionLift = lastRun?.run_summary?.roi?.estimated_conversion_lift_pct || 0;

    // Canvas refs
    const canvas1Ref = useRef<HTMLCanvasElement>(null);
    const canvas2Ref = useRef<HTMLCanvasElement>(null);
    const canvas3Ref = useRef<HTMLCanvasElement>(null);
    const canvas4Ref = useRef<HTMLCanvasElement>(null);

    useEffect(() => {
        function drawSparkline(canvas: HTMLCanvasElement, color: string, data: number[]) {
            const ctx = canvas.getContext('2d');
            if (!ctx) return;
            const width = canvas.width;
            const height = canvas.height;
            
            let currentProgress = 0;
            const animationDuration = 1500; // ms
            const startTime = performance.now();

            function animate(now: number) {
                const elapsed = now - startTime;
                currentProgress = Math.min(elapsed / animationDuration, 1);

                ctx!.clearRect(0, 0, width, height);
                ctx!.beginPath();
                ctx!.strokeStyle = color;
                ctx!.lineWidth = 2;
                ctx!.lineCap = 'round';
                ctx!.lineJoin = 'round';

                const totalPoints = data.length;
                const visiblePoints = Math.ceil(currentProgress * totalPoints);
                const step = width / (totalPoints - 1);

                for(let i = 0; i < visiblePoints; i++) {
                    const x = i * step;
                    const y = height - (data[i] / 100 * height);
                    if(i === 0) ctx!.moveTo(x, y);
                    else ctx!.lineTo(x, y);
                }
                ctx!.stroke();

                // Gradient fill
                if (visiblePoints > 0) {
                    ctx!.lineTo((visiblePoints - 1) * step, height);
                    ctx!.lineTo(0, height);
                    const gradient = ctx!.createLinearGradient(0, 0, 0, height);
                    gradient.addColorStop(0, color + '20');
                    gradient.addColorStop(1, color + '00');
                    ctx!.fillStyle = gradient;
                    ctx!.fill();
                }

                if (currentProgress < 1) {
                    requestAnimationFrame(animate);
                }
            }
            requestAnimationFrame(animate);
        }

        if (canvas1Ref.current) drawSparkline(canvas1Ref.current, '#004e33', [30, 45, 35, 60, 55, 70, 85, 80, 95, lastScore > 0 ? lastScore : 98]);
        if (canvas2Ref.current) drawSparkline(canvas2Ref.current, '#003d9b', [20, 50, 40, 60, 45, 80, 70, 90, 85, Math.min(100, 85 + lastDelta)]);
        if (canvas3Ref.current) drawSparkline(canvas3Ref.current, '#4c5e85', [90, 92, 88, 95, 99, 97, 98, 99, 99, 99]);
        if (canvas4Ref.current) drawSparkline(canvas4Ref.current, '#737685', [40, 30, 50, 45, 60, 55, 70, 65, 80, totalFixes > 0 ? totalFixes * 10 : 75]);
    }, [lastScore, lastDelta, totalFixes]);

    return (
        <>
            {/* Hero Section */}
            <section className="mb-xxl flex justify-between items-end animate-fade-slide-up opacity-0 stagger-1">
                <div>
                    <h2 className="font-headline-lg text-headline-lg text-on-surface mb-sm">Platform Overview</h2>
                    <p className="font-body-lg text-body-lg text-on-surface-variant max-w-2xl">Executive summary of regional cluster performance and automated optimization outcomes across all enterprise environments.</p>
                </div>
                
                <button 
                    onClick={() => setIsRunModalOpen(true)}
                    className="bg-primary text-on-primary px-xl py-md rounded-lg flex items-center gap-md font-headline-sm text-headline-sm hover:bg-primary-container active:scale-95 transition-all duration-200 shadow-sm"
                >
                    <span className="material-symbols-outlined transition-transform group-hover:rotate-90">add_circle</span>
                    <span>New Optimization</span>
                </button>
            </section>

            {/* KPI Grid */}
            <section className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-lg mb-xxl">
                {/* KPI Card 1 */}
                <div className="bg-surface-container-lowest p-lg rounded-xl border border-outline-variant shadow-[0_4px_20px_rgba(0,0,0,0.04)] animate-fade-slide-up opacity-0 stagger-2 hover-lift">
                    <div className="flex justify-between items-start mb-md">
                        <span className="text-on-surface-variant font-label-md text-label-md">Global Site Health</span>
                        <span className="text-tertiary-container bg-tertiary/10 px-sm py-xs rounded font-label-md text-label-md font-bold animate-soft-pulse">Stable</span>
                    </div>
                    <div className="flex items-baseline gap-sm mb-md">
                        <h3 className="font-headline-lg text-headline-lg">{lastScore.toFixed(1)}%</h3>
                    </div>
                    <div className="h-12 w-full">
                        <canvas ref={canvas1Ref} className="w-full h-full"></canvas>
                    </div>
                </div>

                {/* KPI Card 2 */}
                <div className="bg-surface-container-lowest p-lg rounded-xl border border-outline-variant shadow-[0_4px_20px_rgba(0,0,0,0.04)] animate-fade-slide-up opacity-0 stagger-3 hover-lift">
                    <div className="flex justify-between items-start mb-md">
                        <span className="text-on-surface-variant font-label-md text-label-md">Score Improvement</span>
                        <span className="text-primary-container bg-primary/10 px-sm py-xs rounded font-label-md text-label-md font-bold animate-soft-pulse">Continuous</span>
                    </div>
                    <div className="flex items-baseline gap-sm mb-md">
                        <h3 className="font-headline-lg text-headline-lg">+{lastDelta.toFixed(1)}</h3>
                        <span className="text-tertiary text-sm flex items-center"><span className="material-symbols-outlined text-sm">arrow_upward</span> Points</span>
                    </div>
                    <div className="h-12 w-full">
                        <canvas ref={canvas2Ref} className="w-full h-full"></canvas>
                    </div>
                </div>

                {/* KPI Card 3 */}
                <div className="bg-surface-container-lowest p-lg rounded-xl border border-outline-variant shadow-[0_4px_20px_rgba(0,0,0,0.04)] animate-fade-slide-up opacity-0 stagger-4 hover-lift">
                    <div className="flex justify-between items-start mb-md">
                        <span className="text-on-surface-variant font-label-md text-label-md">Est. Revenue Lift</span>
                        <span className="text-secondary-container bg-secondary/10 px-sm py-xs rounded font-label-md text-label-md font-bold">High Impact</span>
                    </div>
                    <div className="flex items-baseline gap-sm mb-md">
                        <h3 className="font-headline-lg text-headline-lg">+{conversionLift.toFixed(1)}%</h3>
                    </div>
                    <div className="h-12 w-full">
                        <canvas ref={canvas3Ref} className="w-full h-full"></canvas>
                    </div>
                </div>

                {/* KPI Card 4 */}
                <div className="bg-surface-container-lowest p-lg rounded-xl border border-outline-variant shadow-[0_4px_20px_rgba(0,0,0,0.04)] animate-fade-slide-up opacity-0 stagger-5 hover-lift">
                    <div className="flex justify-between items-start mb-md">
                        <span className="text-on-surface-variant font-label-md text-label-md">Optimizations Deployed</span>
                        <span className="text-on-surface-variant bg-surface-container-high px-sm py-xs rounded font-label-md text-label-md font-bold">24h Window</span>
                    </div>
                    <div className="flex items-baseline gap-sm mb-md">
                        <h3 className="font-headline-lg text-headline-lg">{totalFixes}</h3>
                        <span className="text-on-surface-variant text-sm">Total Ops</span>
                    </div>
                    <div className="h-12 w-full">
                        <canvas ref={canvas4Ref} className="w-full h-full"></canvas>
                    </div>
                </div>
            </section>

            {/* Main Section Grid */}
            <div className="grid grid-cols-12 gap-xxl">
                {/* Left Column: Trends & Opportunities */}
                <div className="col-span-12 lg:col-span-8 space-y-xxl">
                    
                    {/* Opportunities Table */}
                    <div className="bg-surface-container-lowest rounded-xl border border-outline-variant overflow-hidden animate-fade-slide-up opacity-0 stagger-4">
                        <div className="p-xl border-b border-outline-variant">
                            <h4 className="font-headline-sm text-headline-sm">Recent Optimizations</h4>
                        </div>
                        <div className="overflow-x-auto">
                            <table className="w-full text-left border-collapse">
                                <thead>
                                    <tr className="bg-surface-container-low">
                                        <th className="px-xl py-md font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Date</th>
                                        <th className="px-xl py-md font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Target Environment</th>
                                        <th className="px-xl py-md font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Primary Metric</th>
                                        <th className="px-xl py-md font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Status</th>
                                        <th className="px-xl py-md font-label-md text-label-md text-on-surface-variant uppercase tracking-wider"></th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-outline-variant">
                                    {loading ? (
                                        <tr><td colSpan={5} className="text-center py-8 text-on-surface-variant">Loading optimizations...</td></tr>
                                    ) : runs.length === 0 ? (
                                        <tr><td colSpan={5} className="text-center py-8 text-on-surface-variant">No active optimizations.</td></tr>
                                    ) : (
                                        runs.slice(0, 10).map((run, i) => {
                                            const sum = run.run_summary || {};
                                            const roi = sum.roi || {};
                                            return (
                                                <tr key={run.run_id || i} className="row-interaction cursor-pointer" onClick={() => router.push(`/live?run_id=${run.id || run.run_id}`)}>
                                                    <td className="px-xl py-md font-body-md text-body-md">
                                                        {run.start_time ? format(new Date(run.start_time), "MMM d, HH:mm") : "-"}
                                                    </td>
                                                    <td className="px-xl py-md">
                                                        <div className="font-body-md text-body-md font-bold truncate max-w-[250px]" title={sum.target_page || run.website_url || "Unknown Target"}>
                                                            {sum.target_page || run.website_url || "Unknown Target"}
                                                        </div>
                                                        <div className="text-xs text-on-surface-variant font-mono mt-xs">
                                                            Run {(run.id || run.run_id).substring(0, 8)}
                                                        </div>
                                                    </td>
                                                    <td className="px-xl py-md font-body-md text-body-md">
                                                        {sum.target_metric || "-"}
                                                    </td>
                                                    <td className="px-xl py-md">
                                                        <div className="flex items-center gap-xs">
                                                            <span className={`w-2 h-2 rounded-full ${run.status === "running" ? "bg-primary animate-pulse" : run.deploy_status === "deployed" ? "bg-tertiary" : "bg-outline"}`}></span>
                                                            <span className="font-body-md text-body-md text-on-surface-variant">{run.deploy_status || run.status || "unknown"}</span>
                                                        </div>
                                                    </td>
                                                    <td className="px-xl py-md text-right">
                                                        <button className="text-primary font-label-md text-label-md font-bold hover:underline transition-all">Review</button>
                                                    </td>
                                                </tr>
                                            );
                                        })
                                    )}
                                </tbody>
                            </table>
                        </div>
                    </div>
                </div>

                {/* Right Column: Intelligence & Health */}
                <div className="col-span-12 lg:col-span-4 space-y-xxl">
                    {/* Intelligence Feed */}
                    <div className="bg-surface-container-lowest p-xl rounded-xl border border-outline-variant h-[500px] flex flex-col animate-fade-slide-up opacity-0 stagger-5">
                        <h4 className="font-headline-sm text-headline-sm mb-xl">Intelligence Feed</h4>
                        <div className="flex-grow overflow-y-auto custom-scrollbar space-y-lg pr-md">
                            {runs.slice(0, 5).map((run, i) => (
                                <div key={run.run_id || i} className="relative pl-xl border-l-2 border-primary/20 pb-md animate-fade-slide-up opacity-0" style={{ animationDelay: `${0.6 + i * 0.1}s` }}>
                                    <div className="absolute -left-[9px] top-0 w-4 h-4 rounded-full bg-primary border-4 border-surface-container-lowest hover:scale-125 transition-transform cursor-crosshair"></div>
                                    <span className="text-xs text-on-surface-variant block mb-1">{run.start_time ? format(new Date(run.start_time), "MMM d, HH:mm") : "-"}</span>
                                    <p className="font-body-md text-body-md font-bold">Optimization Triggered</p>
                                    <p className="text-sm text-on-surface-variant line-clamp-2">Workflow <span className="font-mono">{run.run_id?.substring(0, 8)}</span> executed on <span className="font-bold">{run.run_summary?.target_page || run.website_url || "unknown target"}</span>.</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            </div>

            {/* Run Modal - adapted to Stitch style */}
            {isRunModalOpen && (
                <div className="fixed inset-0 bg-on-surface/50 backdrop-blur-sm z-50 flex items-center justify-center">
                    <div className="bg-surface-container-lowest rounded-xl border border-outline-variant shadow-lg w-full max-w-md min-w-[320px] sm:min-w-[400px] overflow-hidden animate-fade-slide-up">
                        <div className="p-xl border-b border-outline-variant bg-surface-container-low">
                            <h3 className="font-headline-md text-headline-md text-primary">Initialize Optimization Workflow</h3>
                        </div>
                        <div className="p-xl space-y-lg">
                            <div className="flex flex-col gap-sm">
                                <label className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Target Environment URL</label>
                                <input 
                                    className="px-md py-sm bg-surface border border-outline-variant rounded-lg focus:outline-none focus:ring-1 focus:ring-primary focus:border-primary transition-colors font-body-md text-body-md"
                                    value={url}
                                    onChange={(e) => setUrl(e.target.value)}
                                    placeholder="https://yourwebsite.com"
                                />
                            </div>
                            <div className="flex flex-col gap-sm">
                                <label className="font-label-md text-label-md text-on-surface-variant uppercase tracking-wider">Validation Mode</label>
                                <div className="flex items-center gap-xl bg-surface-container-low p-md rounded-lg">
                                    <label className="flex items-center gap-xs cursor-pointer font-body-md text-body-md">
                                        <input 
                                            type="radio" 
                                            name="mode" 
                                            checked={mode === "SUPERVISED"} 
                                            onChange={() => setMode("SUPERVISED")} 
                                        />
                                        <span>Manual Review</span>
                                    </label>
                                    <label className="flex items-center gap-xs cursor-pointer font-body-md text-body-md text-primary font-bold">
                                        <input 
                                            type="radio" 
                                            name="mode" 
                                            checked={mode === "AUTOMATED"} 
                                            onChange={() => setMode("AUTOMATED")} 
                                        />
                                        <span>Fully Automated</span>
                                    </label>
                                </div>
                                <p className="text-xs text-on-surface-variant mt-1">
                                    {mode === "SUPERVISED" 
                                        ? "The system will pause and request executive approval before deploying any optimizations." 
                                        : "The system will automatically deploy optimizations to production if safety gates pass."}
                                </p>
                            </div>
                        </div>
                        <div className="p-xl bg-surface-container-low flex justify-end gap-md border-t border-outline-variant">
                            <button className="px-md py-sm rounded-lg font-label-md text-label-md text-on-surface-variant hover:bg-surface-container-highest transition-colors" onClick={() => setIsRunModalOpen(false)}>Cancel</button>
                            <button 
                                onClick={startRun} 
                                disabled={isSubmitting}
                                className="bg-primary text-on-primary px-xl py-sm rounded-lg font-label-md text-label-md hover:bg-primary-container active:scale-95 transition-all"
                            >
                                {isSubmitting ? "Initializing..." : "Start Workflow"}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
}
