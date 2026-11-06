import React, { useState, useEffect } from 'react';
import { 
  ShieldAlert, 
  Terminal, 
  Play, 
  RefreshCw, 
  Database, 
  Cpu, 
  Network, 
  AlertTriangle, 
  CheckCircle2, 
  Clock, 
  Crown, 
  ChevronLeft, 
  FileUp, 
  Sparkles,
  Search,
  Hash,
  ArrowRight
} from 'lucide-react';
import GraphCanvas from './GraphCanvas';
import EvidenceDossier from './EvidenceDossier';
import { analyzeNetwork, checkBackendHealth } from '../services/api';

const DEFAULT_FIR_TEXT = `FIR No. 45/2026 ki investigation ke dauran, yeh clear ho gaya ki suspect Vikas Kumar urf Bicky Sector 42 se ek illegal hawala operation run kar raha tha. Arrest ke time, uske paas se ek burner mobile number 9876543210 (IMEI: 864201948201948) recover hua. Telecom CDR analysis se pata chala ki this device was in continuous contact with a master number 9123456789 (IMEI: 359876102938475). Financial tracing show karti hai ki Vikas ne total INR 5,00,000 transfer kiye into SBI Account 30291827465, jo ki syndicate mastermind Rajendra Singh @ Raju Bhai dwara strictly control kiya jaata hai.`;

const SAMPLE_PRESETS = [
  {
    name: "FIR 45/2026 (Hawala Ring)",
    text: DEFAULT_FIR_TEXT
  },
  {
    name: "FIR 88/2026 (Telecom Smuggling)",
    text: `During intelligence raid at Old Delhi, accused Amit Verma urf Chhotu was detained with mobile 9988776655 (IMEI: 867543210987654). Interrogation revealed he reported to handler Tariq Khan @ Tiger on phone 9811223344 (IMEI: 354433221100998). Money trail indicates fund transfer of INR 2,50,000 into HDFC Account 50100234567891 belonging to mastermind Vikramaditya Malhotra @ Boss.`
  }
];

export default function TerminalWorkspace({ onBackToLanding }) {
  const [reportText, setReportText] = useState(DEFAULT_FIR_TEXT);
  const [docId, setDocId] = useState("FIR_45_2026");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  
  // Pipeline Step Tracking: 0 = Idle, 1 = AI NER, 2 = Neo4j Ingestion, 3 = Centrality / Complete
  const [pipelineStep, setPipelineStep] = useState(0);

  // Graph Data & Summary
  const [graphData, setGraphData] = useState(null);
  const [summaryData, setSummaryData] = useState(null);
  const [selectedNode, setSelectedNode] = useState(null);
  const [backendStatus, setBackendStatus] = useState({ online: true, checked: false });

  // Check backend health on mount
  useEffect(() => {
    async function checkHealth() {
      const res = await checkBackendHealth();
      setBackendStatus({ online: res.online, checked: true, error: res.error });
    }
    checkHealth();
    // Auto-run initial analysis
    handleExecuteAnalysis(DEFAULT_FIR_TEXT);
  }, []);

  const handleExecuteAnalysis = async (customText = null) => {
    const textToProcess = customText || reportText;
    if (!textToProcess.trim()) {
      setErrorMsg("Please enter or paste surveillance evidence text.");
      return;
    }

    setIsLoading(true);
    setErrorMsg(null);
    setSelectedNode(null);

    // Simulate pipeline step advancement for visual feedback
    setPipelineStep(1);

    try {
      // Step 1: AI Pipeline processing
      const stepTimer1 = setTimeout(() => setPipelineStep(2), 250);
      const stepTimer2 = setTimeout(() => setPipelineStep(3), 500);

      const result = await analyzeNetwork(textToProcess, docId);

      clearTimeout(stepTimer1);
      clearTimeout(stepTimer2);
      setPipelineStep(3);

      setGraphData(result.elements || { nodes: [], edges: [] });
      setSummaryData(result.summary || null);

      // Auto-select Kingpin if detected
      if (result.summary?.kingpin_node_id && result.elements?.nodes) {
        const kp = result.elements.nodes.find(n => n.data.id === result.summary.kingpin_node_id);
        if (kp) {
          setSelectedNode({ ...kp.data, isKingpin: true });
        }
      }
    } catch (err) {
      console.error("Analysis execution error:", err);
      setErrorMsg(err.message || "Failed to communicate with FastAPI backend on http://127.0.0.1:8000.");
      setPipelineStep(0);
    } finally {
      setIsLoading(false);
    }
  };

  const kingpinId = summaryData?.kingpin_node_id;
  const kingpinNode = graphData?.nodes?.find(n => n.data.id === kingpinId);
  const kingpinLabel = kingpinNode ? kingpinNode.data.label : (kingpinId || "None Identified");

  return (
    <div className="flex flex-col h-screen w-screen bg-[#000000] text-slate-100 overflow-hidden font-sans">
      {/* Top Tactical Status Bar */}
      <header className="h-14 bg-[#111827] border-b border-slate-800 flex items-center justify-between px-5 shrink-0 z-30">
        <div className="flex items-center gap-4">
          <button 
            onClick={onBackToLanding}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded bg-black/60 border border-slate-700 text-xs font-mono text-slate-300 hover:text-cyan-400 hover:border-cyan-500/50 transition-colors cursor-pointer"
          >
            <ChevronLeft className="w-3.5 h-3.5" />
            <span>EXECUTIVE VIEW</span>
          </button>

          <div className="h-5 w-[1px] bg-slate-800" />

          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full bg-cyan-500 shadow-neon-cyan animate-pulse" />
            <span className="font-bold text-sm tracking-wider font-mono text-white">
              CRIMI-NEX OS
            </span>
            <span className="text-[11px] font-mono text-slate-400 hidden sm:inline">
              // TACTICAL INTELLIGENCE WORKSPACE
            </span>
          </div>
        </div>

        <div className="flex items-center gap-5">
          {/* 3-Step Pipeline Tracker in Top Header */}
          <div className="hidden lg:flex items-center gap-2 bg-black/60 border border-slate-800 px-3 py-1 rounded-lg text-xs font-mono">
            <span className="text-[10px] text-slate-500 uppercase tracking-widest mr-1">PIPELINE:</span>
            
            {/* Step 1 */}
            <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded ${
              pipelineStep >= 1 ? 'text-cyan-400 bg-cyan-950/40 border border-cyan-500/30 font-semibold' : 'text-slate-600'
            }`}>
              <Cpu className="w-3 h-3" />
              <span>1. Indic AI NER</span>
            </div>
            
            <span className="text-slate-700">→</span>

            {/* Step 2 */}
            <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded ${
              pipelineStep >= 2 ? 'text-purple-400 bg-purple-950/40 border border-purple-500/30 font-semibold' : 'text-slate-600'
            }`}>
              <Database className="w-3 h-3" />
              <span>2. Graph Synthesis</span>
            </div>

            <span className="text-slate-700">→</span>

            {/* Step 3 */}
            <div className={`flex items-center gap-1.5 px-2 py-0.5 rounded ${
              pipelineStep >= 3 ? 'text-emerald-400 bg-emerald-950/40 border border-emerald-500/30 font-semibold' : 'text-slate-600'
            }`}>
              <Crown className="w-3 h-3" />
              <span>3. Kingpin Centrality</span>
            </div>
          </div>

          {/* Backend Status Badge */}
          <div className="flex items-center gap-2 text-xs font-mono bg-black/60 border border-slate-800 px-3 py-1 rounded-lg">
            <span className={`w-2 h-2 rounded-full ${backendStatus.online ? 'bg-emerald-500 shadow-neon-green' : 'bg-red-500 shadow-neon-red'}`} />
            <span className={backendStatus.online ? 'text-emerald-400' : 'text-red-400'}>
              {backendStatus.online ? 'FASTAPI: 8000 ONLINE' : 'BACKEND DISCONNECTED'}
            </span>
          </div>
        </div>
      </header>

      {/* Main Tactical Workspace Split View */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden relative">
        
        {/* Left Side Intelligence Console (Charcoal #111827) */}
        <aside className="w-full md:w-[460px] lg:w-[500px] bg-[#111827] border-r border-slate-800 flex flex-col h-full overflow-y-auto shrink-0 z-20 shadow-2xl">
          <div className="p-5 space-y-5">
            
            {/* Case Identifier Header */}
            <div className="flex items-center justify-between">
              <div>
                <span className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-widest block">
                  CASE DOSSIER ID
                </span>
                <input 
                  type="text" 
                  value={docId}
                  onChange={(e) => setDocId(e.target.value)}
                  className="bg-black/80 border border-slate-800 rounded px-2 py-1 text-xs font-mono text-cyan-400 focus:outline-none focus:border-cyan-500 transition-colors mt-0.5"
                />
              </div>

              {/* Preset Scenario Selector */}
              <div className="text-right">
                <span className="text-[10px] font-mono font-bold text-slate-500 uppercase tracking-widest block mb-1">
                  SAMPLE DOSSIERS
                </span>
                <div className="flex gap-1.5">
                  {SAMPLE_PRESETS.map((p, idx) => (
                    <button
                      key={idx}
                      onClick={() => {
                        setReportText(p.text);
                        handleExecuteAnalysis(p.text);
                      }}
                      className="text-[10px] font-mono px-2 py-0.5 rounded bg-black/60 border border-slate-700 text-slate-300 hover:text-cyan-400 hover:border-cyan-500 transition-colors cursor-pointer"
                    >
                      P{idx + 1}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Evidence Dropzone & Textarea Area */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <label className="text-[11px] font-mono font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                  <FileUp className="w-3.5 h-3.5 text-cyan-400" />
                  <span>SURVEILLANCE REPORT / EVIDENCE FEED</span>
                </label>
                <span className="text-[10px] font-mono text-slate-500">
                  {reportText.length} chars
                </span>
              </div>

              <div className="relative group">
                <textarea
                  value={reportText}
                  onChange={(e) => setReportText(e.target.value)}
                  placeholder="Paste FIR narrative, interrogation transcripts, burner phone CDRs, or hawala transaction logs here..."
                  className="w-full h-36 bg-[#000000] border border-slate-800 rounded-xl p-3 text-xs font-mono text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-cyan-500/70 focus:ring-1 focus:ring-cyan-500/30 transition-all resize-none leading-relaxed"
                />
              </div>

              {/* Action Buttons */}
              <button
                onClick={() => handleExecuteAnalysis()}
                disabled={isLoading}
                className="w-full py-3 rounded-xl bg-gradient-to-r from-cyan-500 via-blue-600 to-cyan-500 bg-size-200 hover:bg-pos-100 text-black font-bold text-xs font-mono tracking-wider flex items-center justify-center gap-2.5 shadow-neon-cyan transition-all duration-200 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed active:scale-95"
              >
                {isLoading ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin text-black" />
                    <span>DECONSTRUCTING SYNDICATE PIPELINE...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-black text-black" />
                    <span>EXECUTE NETWORK ANALYSIS</span>
                  </>
                )}
              </button>
            </div>

            {/* Error Message Alert */}
            {errorMsg && (
              <div className="p-3.5 rounded-xl bg-red-950/40 border border-red-500/60 text-red-300 text-xs font-mono flex items-start gap-2.5">
                <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <span className="font-bold text-red-200 block">PIPELINE EXECUTION BLOCKED</span>
                  <p className="text-[11px] text-red-300/90 leading-relaxed">{errorMsg}</p>
                  <p className="text-[10px] text-slate-400">
                    Verify FastAPI is running: <code className="text-cyan-400 bg-black/60 px-1 py-0.5 rounded">uvicorn backend.main:app --reload</code>
                  </p>
                </div>
              </div>
            )}

            {/* Tactical Syndicate KPI Summary Card */}
            {summaryData && (
              <div className="bg-[#000000] border border-slate-800 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between border-b border-slate-800 pb-2">
                  <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest flex items-center gap-1.5">
                    <Sparkles className="w-3.5 h-3.5 text-amber-400" />
                    <span>SYNDICATE TOPOLOGY SUMMARY</span>
                  </span>
                  <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/40 px-2 py-0.5 rounded border border-emerald-500/30">
                    RESOLVED
                  </span>
                </div>

                {/* Kingpin Highlight Banner */}
                <div className="p-3 rounded-lg bg-gradient-to-r from-red-950/50 via-black to-red-950/30 border border-red-500/50 flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <div className="w-8 h-8 rounded-full bg-red-500/20 border border-red-500 flex items-center justify-center text-red-400 shadow-neon-red">
                      <Crown className="w-4 h-4 text-amber-300" />
                    </div>
                    <div>
                      <span className="text-[9px] font-mono text-red-300 uppercase tracking-wider block">
                        IDENTIFIED KINGPIN
                      </span>
                      <span className="text-sm font-bold text-white tracking-tight">
                        {kingpinLabel}
                      </span>
                    </div>
                  </div>
                  <span className="text-xs font-mono font-bold text-amber-300 bg-red-950 px-2 py-1 rounded border border-red-500/40">
                    PRIMARY TARGET
                  </span>
                </div>

                {/* Metric Quick Stats */}
                <div className="grid grid-cols-2 gap-2 text-center">
                  <div className="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
                    <span className="text-[10px] font-mono text-slate-400 block">TOTAL NODES</span>
                    <span className="text-lg font-bold font-mono text-cyan-400">
                      {summaryData.total_nodes || 0}
                    </span>
                  </div>
                  <div className="bg-slate-900/60 p-2 rounded-lg border border-slate-800">
                    <span className="text-[10px] font-mono text-slate-400 block">TOTAL EDGES</span>
                    <span className="text-lg font-bold font-mono text-purple-400">
                      {summaryData.total_edges || 0}
                    </span>
                  </div>
                </div>
              </div>
            )}

            {/* Selected Node Evidence Dossier Panel */}
            <EvidenceDossier 
              node={selectedNode}
              documentHash={summaryData?.document_hash}
              reportText={reportText}
              onClose={() => setSelectedNode(null)}
            />

            {/* Visual Classes Color Legend */}
            <div className="bg-[#000000] border border-slate-800 rounded-xl p-3.5 space-y-2">
              <span className="text-[10px] font-mono font-bold text-slate-400 uppercase tracking-widest block">
                ENTITY VISUAL ONTOLOGY
              </span>
              <div className="grid grid-cols-2 gap-2 text-[11px] font-mono text-slate-300">
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-red-500 border border-amber-300 shadow-neon-red" />
                  <span>Kingpin (Target)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-amber-500 border border-amber-600" />
                  <span>Person / Operative</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-emerald-500 border border-emerald-600" />
                  <span>Phone (MSISDN)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-cyan-500 border border-cyan-400 shadow-neon-cyan" />
                  <span>Device (IMEI)</span>
                </div>
                <div className="flex items-center gap-2 col-span-2">
                  <span className="w-3 h-3 rounded-full bg-purple-500 border border-purple-600" />
                  <span>Financial Account (Bank / UPI)</span>
                </div>
              </div>
            </div>

          </div>
        </aside>

        {/* Right Interactive Graph Canvas (Black #000000) */}
        <section className="flex-1 h-full relative bg-[#000000] overflow-hidden">
          <GraphCanvas 
            elements={graphData}
            kingpinId={kingpinId}
            onSelectNode={(node) => setSelectedNode(node)}
            selectedNodeId={selectedNode?.id}
          />
        </section>

      </div>
    </div>
  );
}

