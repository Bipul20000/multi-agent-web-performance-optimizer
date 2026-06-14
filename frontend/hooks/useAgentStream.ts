"use client";

import { useState, useEffect, useCallback } from "react";

export type AgentStatus = "waiting" | "running" | "complete" | "error" | "failed";

export interface AgentState {
  status: AgentStatus;
  summary?: string;
  duration_ms?: number;
  data?: any;
}

export interface GateResult {
  result: "PASS" | "FAIL" | "APPROVE" | "REJECT" | "CLEAR" | "IMPACTED" | string;
  details?: string;
}

export interface ApprovalRequest {
  run_id: string;
  pr_url: string;
  details?: string;
}

export function useAgentStream(runId: string | null) {
  const [agentStates, setAgentStates] = useState<Record<string, AgentState>>({});
  const [gateResults, setGateResults] = useState<Record<string, GateResult>>({});
  const [fixPlan, setFixPlan] = useState<any | null>(null);
  const [isComplete, setIsComplete] = useState<boolean>(false);
  const [requiresApproval, setRequiresApproval] = useState<ApprovalRequest | null>(null);
  const [latestEvent, setLatestEvent] = useState<any | null>(null);

  const [rawLogs, setRawLogs] = useState<any[]>([]);

  // Hydrate from DB on mount
  useEffect(() => {
    if (runId && typeof window !== 'undefined') {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      fetch(`${apiUrl}/run/${runId}`)
        .then(res => res.json())
        .then(data => {
            if (!data) return;
            
            // Reconstruct history
            if (data.run_summary?.agent_steps) {
                // Map DB agent_steps to the SSE format that the UI expects
                const mappedLogs = data.run_summary.agent_steps.map((step: any) => ({
                    event_type: step.event_type || (step.status === "running" ? "agent_start" : `agent_${step.status}`),
                    agent_name: step.agent_name || step.agent,
                    data: step.data || { summary: step.summary, duration_ms: step.duration_ms },
                    timestamp: step.timestamp || Date.now()
                }));
                
                const savedLogs = sessionStorage.getItem(`awpis_rawLogs_${runId}`);
                if (savedLogs) {
                    try {
                        const parsed = JSON.parse(savedLogs);
                        setRawLogs(parsed.length > mappedLogs.length ? parsed : mappedLogs);
                    } catch (e) {
                        setRawLogs(mappedLogs);
                    }
                } else {
                    setRawLogs(mappedLogs);
                }
                
                const newStates: Record<string, AgentState> = {};
                data.run_summary.agent_steps.forEach((step: any) => {
                    const agentName = step.agent_name;
                    if (!agentName) return;
                    if (step.event_type === "agent_start") {
                        newStates[agentName] = { status: "running", summary: step.data?.summary || step.data?.input_summary };
                    } else if (step.event_type === "agent_complete") {
                        newStates[agentName] = { status: "complete", summary: step.data?.summary || step.data?.output_summary, duration_ms: step.data?.duration_ms };
                    } else if (step.event_type === "agent_error") {
                        newStates[agentName] = { status: "failed", summary: step.data?.error || step.data?.summary, duration_ms: step.data?.duration_ms };
                    }
                });
                
                // Inject metrics if available
                if (data.run_summary?.psi_metrics || data.run_summary?.backend_metrics) {
                    if (!newStates["metrics_agent"]) {
                        newStates["metrics_agent"] = { status: "complete" };
                    }
                    newStates["metrics_agent"].data = {
                        ...(newStates["metrics_agent"].data || {}),
                        psi_metrics: data.run_summary.psi_metrics,
                        backend_metrics: data.run_summary.backend_metrics
                    };
                }
                
                // If run is aborted or failed, mark running agents as failed
                const isEnded = data.status === "aborted" || data.status === "failed" || data.status === "complete" || data.status === "sandbox_failed";
                if (isEnded) {
                    setIsComplete(true);
                    Object.keys(newStates).forEach(k => {
                        if (newStates[k].status === "running") {
                            newStates[k].status = "failed";
                        }
                    });
                }
                
                setAgentStates(prev => ({ ...newStates, ...prev })); // let live events override if they exist
            }
            
            if (data.status === "aborted" || data.status === "failed" || data.status === "complete" || data.status === "sandbox_failed") {
                setIsComplete(true);
                // Clean up any stale running states in session storage
                setAgentStates(prev => {
                    const clean = { ...prev };
                    Object.keys(clean).forEach(k => {
                        if (clean[k].status === "running") clean[k].status = "failed";
                    });
                    return clean;
                });
            }
        })
        .catch(err => console.error("Failed to hydrate run history", err));
        
      // Also try session storage
      const savedStates = sessionStorage.getItem(`awpis_agentStates_${runId}`);
      if (savedStates) setAgentStates(prev => ({ ...prev, ...JSON.parse(savedStates) }));
      
      const savedGates = sessionStorage.getItem(`awpis_gateResults_${runId}`);
      if (savedGates) setGateResults(JSON.parse(savedGates));
      
      const savedComplete = sessionStorage.getItem(`awpis_isComplete_${runId}`);
      if (savedComplete) setIsComplete(JSON.parse(savedComplete));
    }
  }, [runId]);

  useEffect(() => {
    if (runId && typeof window !== 'undefined') {
      sessionStorage.setItem(`awpis_agentStates_${runId}`, JSON.stringify(agentStates));
      sessionStorage.setItem(`awpis_gateResults_${runId}`, JSON.stringify(gateResults));
      sessionStorage.setItem(`awpis_isComplete_${runId}`, JSON.stringify(isComplete));
    }
  }, [runId, agentStates, gateResults, isComplete]);

  useEffect(() => {
    if (!runId) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    const eventSource = new EventSource(`${apiUrl}/stream/${runId}`);

    eventSource.onmessage = (event) => {
      try {
        console.log("SSE Event Data:", event.data);
        const eventJson = JSON.parse(event.data);
        const eventType = eventJson.event_type;
        
        // Ignore SSE keep-alive pings
        if (eventType === "ping") return;

        const agentName = eventJson.agent_name;
        const data = eventJson.data || {};
        
        setLatestEvent(eventJson);

        if (eventType === "agent_start") {
          setAgentStates((prev) => ({
            ...prev,
            [agentName]: { ...prev[agentName], status: "running", summary: data.input_summary || data.summary }
          }));
        } 
        else if (eventType === "agent_complete") {
          setAgentStates((prev) => ({
            ...prev,
            [agentName]: { 
              ...prev[agentName],
              status: "complete", 
              summary: data.output_summary || data.summary, 
              duration_ms: data.duration_ms 
            }
          }));
        }
        else if (eventType === "agent_error") {
          setAgentStates((prev) => ({
            ...prev,
            [agentName]: { 
              ...prev[agentName],
              status: "failed", 
              summary: data.error || data.summary, 
              duration_ms: data.duration_ms 
            }
          }));
        }
        else if (eventType === "metric_update") {
          setAgentStates((prev) => ({
            ...prev,
            [agentName]: {
                ...prev[agentName] || { status: "running" },
                data: { ...(prev[agentName]?.data || {}), ...data.metrics }
            }
          }));
          
          // Check for human approval in metric update
          if (data.metrics?.type === "human_approval_required") {
            setRequiresApproval({
              run_id: runId,
              pr_url: data.metrics.pr_url || "",
              details: data.metrics.message
            });
          }
        }

        if (eventType === "gate_result") {
          setGateResults((prev) => ({
            ...prev,
            [agentName]: { result: data.result, details: data.details }
          }));
        }
        else if (eventType === "run_complete") {
          setIsComplete(true);
          if (data.fix_plan) {
            setFixPlan(data.fix_plan);
          }
          eventSource.close();
        }
        else if (eventType === "run_error") {
          setIsComplete(true);
          eventSource.close();
        }
      } catch (err) {
        console.error("Failed to parse SSE message", err);
      }
    };

    eventSource.onerror = (err) => {
      console.error("SSE connection error", err);
      eventSource.close();
    };

    return () => {
      eventSource.close();
    };
  }, [runId]);

  return {
    agentStates,
    gateResults,
    fixPlan,
    isComplete,
    requiresApproval,
    latestEvent,
    rawLogs,
    setRawLogs
  };
}
