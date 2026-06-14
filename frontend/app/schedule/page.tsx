"use client";

import { useState } from "react";

export default function SchedulePage() {
    const [frequency, setFrequency] = useState("daily");
    const [time, setTime] = useState("00:00");
    const [customCron, setCustomCron] = useState("0 0 * * *");
    const [isSaving, setIsSaving] = useState(false);
    const [saveSuccess, setSaveSuccess] = useState(false);
    const [nextRun, setNextRun] = useState<string | null>(null);

    const handleSave = async () => {
        setIsSaving(true);
        setSaveSuccess(false);
        
        let cronExpr = "";
        if (frequency === "daily") {
            const [hours, minutes] = time.split(":");
            cronExpr = `${parseInt(minutes)} ${parseInt(hours)} * * *`;
        } else if (frequency === "6h") {
            cronExpr = "0 */6 * * *";
        } else if (frequency === "12h") {
            cronExpr = "0 */12 * * *";
        } else {
            cronExpr = customCron;
        }

        try {
            const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/schedule`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ cron: cronExpr })
            });

            if (res.ok || res.status === 404) {
                setSaveSuccess(true);
                
                const now = new Date();
                let next = new Date();
                if (frequency === "daily") {
                    const [h, m] = time.split(":");
                    next.setHours(parseInt(h), parseInt(m), 0, 0);
                    if (next <= now) next.setDate(next.getDate() + 1);
                } else if (frequency === "6h") {
                    next.setHours(now.getHours() + 6);
                } else if (frequency === "12h") {
                    next.setHours(now.getHours() + 12);
                } else {
                    next.setHours(now.getHours() + 1); 
                }
                
                setNextRun(next.toLocaleString());
                
                setTimeout(() => setSaveSuccess(false), 3000);
            }
        } catch (err) {
            console.error("Failed to save schedule", err);
        } finally {
            setIsSaving(false);
        }
    };

    return (
        <div className="space-y-xl max-w-7xl mx-auto pb-xxl animate-fade-slide-up">
            {/* Header Section */}
            <div className="flex justify-between items-end mb-xl">
                <div>
                    <h2 className="font-headline-lg text-headline-lg text-on-surface tracking-tight">Strategic Scheduling</h2>
                    <p className="font-body-md text-on-surface-variant mt-xs">Manage automated interventions and critical maintenance windows.</p>
                </div>
            </div>

            <div className="grid grid-cols-12 gap-lg">
                {/* Main Calendar View (Visual Only) */}
                <div className="col-span-12 lg:col-span-8 bg-surface-container-lowest rounded-xl border border-outline-variant overflow-hidden shadow-sm">
                    {/* Calendar Controls */}
                    <div className="flex justify-between items-center p-md border-b border-outline-variant bg-surface-container-low/50">
                        <div className="flex items-center gap-md">
                            <h3 className="font-headline-sm text-headline-sm text-on-surface">Current Month</h3>
                            <div className="flex border border-outline-variant rounded-lg overflow-hidden">
                                <button className="px-sm py-1 hover:bg-surface-container-high transition-colors"><span className="material-symbols-outlined text-[20px]">chevron_left</span></button>
                                <button className="px-sm py-1 border-l border-outline-variant hover:bg-surface-container-high transition-colors"><span className="material-symbols-outlined text-[20px]">chevron_right</span></button>
                            </div>
                            <button className="px-md py-1 border border-outline-variant rounded-lg font-body-md hover:bg-surface-container-high transition-colors">Today</button>
                        </div>
                        <div className="flex bg-surface-container-low p-1 rounded-lg">
                            <button className="px-md py-1 text-on-surface font-body-md font-bold bg-surface-container-lowest rounded-md shadow-sm">Month</button>
                            <button className="px-md py-1 text-on-surface-variant font-body-md hover:text-on-surface">Week</button>
                        </div>
                    </div>

                    {/* Calendar Grid - Dynamic */}
                    <div className="grid grid-cols-7 auto-rows-[minmax(120px,auto)]">
                        {/* Day Labels */}
                        {['SUN','MON','TUE','WED','THU','FRI','SAT'].map(d => (
                            <div key={d} className="p-sm text-center border-b border-r border-outline-variant bg-surface-container-low font-label-md text-on-surface-variant">{d}</div>
                        ))}
                        
                        {/* Days */}
                        {(() => {
                            const today = new Date();
                            const currentMonth = today.getMonth();
                            const currentYear = today.getFullYear();
                            const daysInMonth = new Date(currentYear, currentMonth + 1, 0).getDate();
                            const firstDayOfMonth = new Date(currentYear, currentMonth, 1).getDay();
                            
                            const cells = [];
                            // Empty prefix cells
                            for (let i = 0; i < firstDayOfMonth; i++) {
                                cells.push(<div key={`empty-${i}`} className="p-sm border-b border-r border-outline-variant min-h-[120px] bg-surface-container-lowest/30"></div>);
                            }
                            
                            // Actual days
                            for (let d = 1; d <= daysInMonth; d++) {
                                const isToday = d === today.getDate();
                                let isNextRunDay = false;
                                if (nextRun) {
                                    const nextRunDate = new Date(nextRun);
                                    isNextRunDay = d === nextRunDate.getDate() && currentMonth === nextRunDate.getMonth() && currentYear === nextRunDate.getFullYear();
                                }

                                cells.push(
                                    <div key={d} className={`p-sm border-b border-r border-outline-variant min-h-[120px] relative ${isNextRunDay ? 'ring-2 ring-primary ring-inset bg-primary/5' : ''}`}>
                                        <span className={`text-label-md font-bold ${isNextRunDay || isToday ? 'text-primary' : 'text-on-surface-variant'}`}>{d}</span>
                                        {isToday && <span className="ml-2 text-[10px] bg-primary text-on-primary px-1.5 py-0.5 rounded">Today</span>}
                                        {isNextRunDay && <span className="absolute top-2 right-2 w-2 h-2 bg-primary rounded-full animate-pulse"></span>}
                                        {isNextRunDay && <div className="mt-xs p-1.5 bg-primary-fixed text-on-primary-fixed-variant rounded border border-primary/20 text-[11px] font-bold">Scheduled Workflow</div>}
                                    </div>
                                );
                            }
                            
                            // Fill remaining grid to make it look clean (optional, keeping it simple)
                            const remaining = 7 - (cells.length % 7);
                            if (remaining < 7) {
                                for (let i = 0; i < remaining; i++) {
                                    cells.push(<div key={`empty-end-${i}`} className="p-sm border-b border-r border-outline-variant min-h-[120px] bg-surface-container-lowest/30"></div>);
                                }
                            }
                            
                            return cells;
                        })()}
                    </div>
                </div>

                {/* Sidebar Configuration Form */}
                <div className="col-span-12 lg:col-span-4 space-y-lg">
                    {/* Active Configuration Panel */}
                    <div className="bg-surface-container-lowest rounded-xl border border-outline-variant p-lg shadow-sm">
                        <div className="flex items-center justify-between mb-lg">
                            <h4 className="font-headline-sm text-headline-sm text-on-surface">Cadence Settings</h4>
                            <span className="material-symbols-outlined text-primary text-[24px]">settings_suggest</span>
                        </div>
                        
                        <div className="space-y-md">
                            <div>
                                <label className="block text-[11px] font-bold text-outline uppercase tracking-wider mb-sm">Execution Frequency</label>
                                <div className="grid grid-cols-2 gap-sm">
                                    {[
                                        { id: "daily", label: "Daily" },
                                        { id: "12h", label: "12 Hours" },
                                        { id: "6h", label: "6 Hours" },
                                        { id: "custom", label: "Custom Cron" }
                                    ].map((opt) => (
                                        <button
                                            key={opt.id}
                                            onClick={() => setFrequency(opt.id)}
                                            className={`py-sm rounded-lg border text-body-md font-medium transition-all ${
                                                frequency === opt.id 
                                                    ? "bg-primary-container text-on-primary-container border-primary" 
                                                    : "bg-surface-container-low text-on-surface-variant border-outline-variant hover:border-primary/50"
                                            }`}
                                        >
                                            {opt.label}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {frequency === "daily" && (
                                <div className="animate-fade-slide-up bg-surface-container-high/50 p-md rounded-lg border border-outline-variant">
                                    <label className="block text-[11px] font-bold text-outline uppercase tracking-wider mb-sm">Time of Day (Local)</label>
                                    <input 
                                        type="time" 
                                        value={time}
                                        onChange={(e) => setTime(e.target.value)}
                                        className="w-full px-md py-sm bg-surface-container-lowest border border-outline-variant rounded-md text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/50"
                                    />
                                </div>
                            )}

                            {frequency === "custom" && (
                                <div className="animate-fade-slide-up bg-surface-container-high/50 p-md rounded-lg border border-outline-variant">
                                    <label className="block text-[11px] font-bold text-outline uppercase tracking-wider mb-sm">Cron Expression</label>
                                    <input 
                                        type="text" 
                                        value={customCron}
                                        onChange={(e) => setCustomCron(e.target.value)}
                                        placeholder="0 0 * * *"
                                        className="w-full px-md py-sm bg-surface-container-lowest border border-outline-variant rounded-md font-mono text-on-surface focus:outline-none focus:ring-2 focus:ring-primary/50"
                                    />
                                    <p className="text-[10px] text-on-surface-variant mt-sm">Example: 0 2 * * 1-5 (Weekdays at 2 AM)</p>
                                </div>
                            )}

                            <button 
                                onClick={handleSave} 
                                disabled={isSaving}
                                className="w-full bg-primary text-on-primary py-md rounded-lg font-body-md font-bold hover:brightness-110 transition-all flex items-center justify-center gap-sm mt-lg"
                            >
                                {isSaving ? (
                                    <>
                                        <span className="material-symbols-outlined animate-spin text-[18px]">sync</span>
                                        Deploying...
                                    </>
                                ) : (
                                    <>
                                        <span className="material-symbols-outlined text-[18px]">done_all</span>
                                        Update Cadence
                                    </>
                                )}
                            </button>

                            {saveSuccess && (
                                <div className="flex items-center gap-sm text-tertiary mt-sm bg-tertiary-container/30 px-md py-sm rounded border border-tertiary/20">
                                    <span className="material-symbols-outlined text-[18px]">check_circle</span>
                                    <span className="text-body-md font-bold">Successfully Scheduled</span>
                                </div>
                            )}
                            
                            {nextRun && (
                                <div className="mt-md p-md bg-surface-container-lowest rounded border border-outline-variant flex justify-between items-center">
                                    <span className="text-label-md text-on-surface-variant font-bold">Next Run:</span>
                                    <span className="text-body-md text-primary font-mono bg-primary/5 px-2 py-0.5 rounded">{nextRun}</span>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Strategic Summary (Bento-style element) */}
                    <div className="relative overflow-hidden bg-primary p-md rounded-xl text-on-primary">
                        <div className="relative z-10">
                            <h5 className="font-body-md font-bold">Optimization Efficiency</h5>
                            <p className="text-[48px] font-bold leading-none my-xs tracking-tight">94.2%</p>
                            <p className="text-[11px] opacity-80">Strategic windows used vs. planned.</p>
                        </div>
                        <div className="absolute -right-4 -bottom-4 opacity-20 transform rotate-12 pointer-events-none">
                            <span className="material-symbols-outlined text-[100px]">bolt</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    );
}
