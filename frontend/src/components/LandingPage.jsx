import React from 'react';
import { 
  ShieldAlert, 
  Terminal, 
  Cpu, 
  Network, 
  Fingerprint, 
  Scale, 
  ArrowRight, 
  Activity, 
  Database,
  Lock,
  Layers,
  Sparkles
} from 'lucide-react';

export default function LandingPage({ onLaunchTerminal }) {
  return (
    <div className="min-h-screen bg-black text-slate-100 flex flex-col relative overflow-hidden cyber-grid">
      {/* Top Ambient Glows */}
      <div className="absolute top-0 left-1/4 w-96 h-96 bg-cyan-500/10 rounded-full blur-3xl pointer-events-none" />
      <div className="absolute top-20 right-1/4 w-96 h-96 bg-red-500/10 rounded-full blur-3xl pointer-events-none" />

      {/* Navigation Header */}
      <header className="border-b border-slate-800/80 bg-black/80 backdrop-blur-md sticky top-0 z-50 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-slate-900 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shadow-neon-cyan">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-bold text-lg tracking-wider text-slate-100">CRIMI-NEX</span>
                <span className="text-[10px] px-2 py-0.5 rounded border border-cyan-500/30 text-cyan-400 bg-cyan-950/40 font-mono font-semibold">
                  MIL-SPEC // v2.4
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-mono tracking-tight">KAVACH CRIMINAL INTELLIGENCE SUITE</p>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <div className="hidden md:flex items-center gap-2 text-xs font-mono text-emerald-400 bg-emerald-950/30 border border-emerald-500/30 px-3 py-1.5 rounded-full">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping inline-block" />
              <span>DEFENSE ENGINE OPERATIONAL</span>
            </div>

            <button
              onClick={onLaunchTerminal}
              className="group flex items-center gap-2 text-xs font-semibold px-4 py-2 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 text-black hover:from-cyan-400 hover:to-blue-500 transition-all duration-200 shadow-neon-cyan active:scale-95 cursor-pointer"
            >
              <Terminal className="w-4 h-4 text-black group-hover:rotate-12 transition-transform" />
              <span>LAUNCH TERMINAL</span>
              <ArrowRight className="w-3.5 h-3.5 text-black group-hover:translate-x-1 transition-transform" />
            </button>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <main className="flex-1 max-w-7xl mx-auto px-6 py-16 flex flex-col justify-center items-center text-center relative z-10">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-slate-900/90 border border-cyan-500/30 text-cyan-400 text-xs font-mono tracking-wide mb-8 shadow-lg">
          <Sparkles className="w-3.5 h-3.5" />
          <span>AUTONOMOUS GRAPH SYNDICATE DECONSTRUCTION</span>
        </div>

        <h1 className="text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight max-w-5xl text-transparent bg-clip-text bg-gradient-to-b from-white via-slate-200 to-slate-400 leading-[1.1] mb-6">
          From Scattered Evidence to <span className="text-transparent bg-clip-text bg-gradient-to-r from-red-500 via-orange-400 to-amber-300 drop-shadow-[0_0_35px_rgba(239,68,68,0.4)]">Shattered Syndicates</span>
        </h1>

        <p className="max-w-3xl text-slate-400 text-base sm:text-lg lg:text-xl font-normal leading-relaxed mb-12">
          Transform unstructured multilingual FIR narratives, burner CDR records, and clandestine hawala bank flows into actionable intelligence graphs. Detect hidden syndicate kingpins with mathematical precision in seconds.
        </p>

        {/* Executive Metric Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 w-full max-w-5xl mb-14">
          {/* Metric 1 */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-6 flex flex-col items-center justify-center relative overflow-hidden group hover:border-red-500/50 transition-all duration-300">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-transparent via-red-500 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            <span className="text-4xl sm:text-5xl font-black text-red-500 tracking-tight font-mono mb-2 drop-shadow-[0_0_20px_rgba(239,68,68,0.3)]">
              3 Weeks
            </span>
            <span className="text-xs uppercase tracking-wider font-semibold text-slate-300 mb-1">
              Investigation Cycle
            </span>
            <p className="text-[11px] text-slate-500 leading-snug">
              Reduced from 9+ months of manual dossier compiling to under 21 days
            </p>
          </div>

          {/* Metric 2 */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-6 flex flex-col items-center justify-center relative overflow-hidden group hover:border-emerald-500/50 transition-all duration-300">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-transparent via-emerald-500 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            <span className="text-4xl sm:text-5xl font-black text-emerald-400 tracking-tight font-mono mb-2 drop-shadow-[0_0_20px_rgba(16,185,129,0.3)]">
              ₹0
            </span>
            <span className="text-xs uppercase tracking-wider font-semibold text-slate-300 mb-1">
              Proprietary Licensing Cost
            </span>
            <p className="text-[11px] text-slate-500 leading-snug">
              100% sovereign open-source stack eliminating expensive foreign software dependency
            </p>
          </div>

          {/* Metric 3 */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-6 flex flex-col items-center justify-center relative overflow-hidden group hover:border-cyan-500/50 transition-all duration-300">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-transparent via-cyan-500 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            <span className="text-4xl sm:text-5xl font-black text-cyan-400 tracking-tight font-mono mb-2 drop-shadow-[0_0_20px_rgba(6,182,212,0.3)]">
              100%
            </span>
            <span className="text-xs uppercase tracking-wider font-semibold text-slate-300 mb-1">
              Cryptographic Provenance
            </span>
            <p className="text-[11px] text-slate-500 leading-snug">
              SHA-256 evidence hashing guaranteeing court-admissible chain of custody
            </p>
          </div>

          {/* Metric 4 */}
          <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-6 flex flex-col items-center justify-center relative overflow-hidden group hover:border-amber-500/50 transition-all duration-300">
            <div className="absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-transparent via-amber-500 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />
            <span className="text-4xl sm:text-5xl font-black text-amber-400 tracking-tight font-mono mb-2 drop-shadow-[0_0_20px_rgba(245,158,11,0.3)]">
              &lt; 1.2s
            </span>
            <span className="text-xs uppercase tracking-wider font-semibold text-slate-300 mb-1">
              Real-Time Inference
            </span>
            <p className="text-[11px] text-slate-500 leading-snug">
              FastAPI + NetworkX composite graph centrality and Kingpin detection
            </p>
          </div>
        </div>

        {/* CTA Launch Section */}
        <div className="flex flex-col sm:flex-row items-center gap-4">
          <button
            onClick={onLaunchTerminal}
            className="w-full sm:w-auto px-8 py-4 rounded-xl bg-cyan-500 hover:bg-cyan-400 text-black font-bold text-sm tracking-wider flex items-center justify-center gap-3 shadow-[0_0_30px_rgba(6,182,212,0.4)] hover:shadow-[0_0_40px_rgba(6,182,212,0.6)] transition-all duration-200 cursor-pointer active:scale-95"
          >
            <Terminal className="w-5 h-5 text-black" />
            <span>LAUNCH TACTICAL TERMINAL</span>
            <ArrowRight className="w-4 h-4 text-black" />
          </button>
        </div>
      </main>

      {/* Feature Pillar Highlights */}
      <section className="border-t border-slate-800/80 bg-slate-950/60 py-12 px-6">
        <div className="max-w-7xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="flex items-start gap-4 p-4 rounded-lg bg-black/40 border border-slate-800/60">
            <div className="p-3 rounded-lg bg-orange-950/40 text-orange-400 border border-orange-500/20 shrink-0">
              <Cpu className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-200 text-sm mb-1">Indic Multilingual Extraction</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Seamlessly extracts entities across Hinglish, Hindi, and Indian law enforcement jargon without manual rule writing.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4 p-4 rounded-lg bg-black/40 border border-slate-800/60">
            <div className="p-3 rounded-lg bg-red-950/40 text-red-400 border border-red-500/20 shrink-0">
              <Network className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-200 text-sm mb-1">Mathematical Kingpin Scoring</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Applies composite Degree, Betweenness, and Eigenvector centrality to mathematically isolate syndicate leaders.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-4 p-4 rounded-lg bg-black/40 border border-slate-800/60">
            <div className="p-3 rounded-lg bg-cyan-950/40 text-cyan-400 border border-cyan-500/20 shrink-0">
              <Scale className="w-6 h-6" />
            </div>
            <div>
              <h3 className="font-semibold text-slate-200 text-sm mb-1">Court-Admissible Provenance</h3>
              <p className="text-xs text-slate-400 leading-relaxed">
                Every extracted relationship links directly back to exact character spans and SHA-256 evidence hashes for legal compliance.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-slate-900 bg-black px-6 py-4 text-center text-xs text-slate-600 font-mono">
        KAVACH DEFENSE PLATFORM // AI-POWERED CRIMINAL NETWORK INVESTIGATION // SIH26189
      </footer>
    </div>
  );
}

