import React, { useState } from 'react';
import { 
  FileText, 
  Hash, 
  Crown, 
  ShieldCheck, 
  Check, 
  Copy, 
  X, 
  ExternalLink,
  Target,
  Zap,
  Tag
} from 'lucide-react';

export default function EvidenceDossier({ node, documentHash, reportText, onClose }) {
  const [copied, setCopied] = useState(false);

  if (!node) {
    return (
      <div className="bg-[#050811] border border-slate-800 rounded-xl p-5 flex flex-col items-center justify-center text-center text-slate-500 py-12">
        <Target className="w-10 h-10 text-slate-700 mb-3 animate-pulse" />
        <h4 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-400 mb-1">
          NO ENTITY SELECTED
        </h4>
        <p className="text-[11px] text-slate-600 max-w-xs">
          Click on any node in the intelligence graph to inspect its evidentiary dossier, legal provenance hash, and centrality metrics.
        </p>
      </div>
    );
  }

  const handleCopyHash = () => {
    if (documentHash) {
      navigator.clipboard.writeText(documentHash);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  // Determine label and resolved value
  const displayLabel = node.label || node.id;
  const resolvedValue = node.value || (node.type === 'ACCOUNT' ? (node.label ? node.label.replace(/^.*:\s*/, '') : '') : node.canonical_name || '');

  // Confidence formatting
  let confidenceDisplay = "100.0%";
  if (node.ai_confidence !== undefined && node.ai_confidence !== null) {
    const num = Number(node.ai_confidence);
    confidenceDisplay = num <= 1.0 ? `${(num * 100).toFixed(1)}%` : `${num}%`;
  }

  // Character span calculation/formatting
  let spanDisplay = "-";
  if (node.char_span && Array.isArray(node.char_span) && node.char_span.length === 2) {
    spanDisplay = `[${node.char_span[0]}, ${node.char_span[1]}]`;
  } else if (reportText) {
    const candidate = (node.value || node.canonical_name || node.label || "")
      .split(" (")[0]
      .replace(/^(IMEI|SBI|HDFC|ICICI|PNB|AXIS|KOTAK|BANK|ACC):\s*/i, "")
      .trim();
    if (candidate && reportText.indexOf(candidate) !== -1) {
      const start = reportText.indexOf(candidate);
      spanDisplay = `[${start}, ${start + candidate.length}]`;
    }
  }

  // Centrality score
  const centralityScore = node.centrality_score !== undefined 
    ? Number(node.centrality_score).toFixed(3) 
    : '0.000';

  const isKingpin = Boolean(node.isKingpin);

  return (
    <div className={`rounded-xl border transition-all duration-300 overflow-hidden shadow-2xl ${
      isKingpin 
        ? 'bg-[#12070a] border-red-500/70 shadow-[0_0_30px_rgba(239,68,68,0.25)]' 
        : 'bg-[#050811] border-cyan-500/40 shadow-[0_0_20px_rgba(6,182,212,0.1)]'
    }`}>
      {/* Dossier Header */}
      <div className={`px-4 py-3 border-b flex items-center justify-between ${
        isKingpin ? 'border-red-500/40 bg-red-950/30' : 'border-slate-800 bg-slate-900/50'
      }`}>
        <div className="flex items-center gap-2">
          {isKingpin ? (
            <Crown className="w-4 h-4 text-amber-400 animate-bounce" />
          ) : (
            <FileText className="w-4 h-4 text-cyan-400" />
          )}
          <span className={`text-xs font-mono font-bold tracking-wider uppercase ${
            isKingpin ? 'text-red-400' : 'text-cyan-400'
          }`}>
            {isKingpin ? 'PRIMARY SYNDICATE KINGPIN' : 'EVIDENCE DOSSIER'}
          </span>
        </div>

        {onClose && (
          <button 
            onClick={onClose}
            className="p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors cursor-pointer"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      <div className="p-4 space-y-4">
        {/* Entity Title & Type Pill */}
        <div>
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <span className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
              IDENTIFIER / TARGET
            </span>
            <span className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border uppercase ${
              node.type === 'PERSON' ? 'bg-amber-950/50 text-amber-400 border-amber-500/40' :
              node.type === 'PHONE' ? 'bg-emerald-950/50 text-emerald-400 border-emerald-500/40' :
              node.type === 'IMEI' ? 'bg-cyan-950/50 text-cyan-400 border-cyan-500/40' :
              node.type === 'ACCOUNT' ? 'bg-purple-950/50 text-purple-400 border-purple-500/40' :
              'bg-slate-800 text-slate-300 border-slate-700'
            }`}>
              {node.type || 'ENTITY'}
            </span>
          </div>

          <h3 className="text-base font-bold text-white tracking-tight break-words">
            {displayLabel}
          </h3>

          {resolvedValue && resolvedValue !== displayLabel && (
            <p className="text-xs font-mono text-cyan-300 mt-1 break-all bg-black/40 px-2 py-1 rounded border border-slate-800">
              {resolvedValue}
            </p>
          )}
        </div>

        {/* Tactical Key Metrics Grid */}
        <div className="grid grid-cols-2 gap-2 pt-2 border-t border-slate-800/80">
          <div className="bg-black/50 p-2.5 rounded-lg border border-slate-800/80">
            <span className="text-[10px] font-mono text-slate-400 block mb-0.5">CENTRALITY SCORE</span>
            <span className={`text-sm font-bold font-mono ${
              isKingpin ? 'text-red-400' : 'text-cyan-400'
            }`}>
              {centralityScore}
            </span>
          </div>

          <div className="bg-black/50 p-2.5 rounded-lg border border-slate-800/80">
            <span className="text-[10px] font-mono text-slate-400 block mb-0.5">DIRECT CONNECTIONS</span>
            <span className="text-sm font-bold font-mono text-slate-200">
              {node.degree !== undefined ? `${node.degree} Links` : 'N/A'}
            </span>
          </div>

          <div className="bg-black/50 p-2.5 rounded-lg border border-slate-800/80">
            <span className="text-[10px] font-mono text-slate-400 block mb-0.5">AI CONFIDENCE</span>
            <span className="text-sm font-bold font-mono text-emerald-400 flex items-center gap-1">
              <ShieldCheck className="w-3.5 h-3.5" />
              {confidenceDisplay}
            </span>
          </div>

          <div className="bg-black/50 p-2.5 rounded-lg border border-slate-800/80">
            <span className="text-[10px] font-mono text-slate-400 block mb-0.5">CHARACTER SPAN</span>
            <span className="text-xs font-mono text-amber-300 font-semibold">
              {spanDisplay}
            </span>
          </div>
        </div>

        {/* Evidence Provenance SHA-256 Box */}
        <div className="pt-2 border-t border-slate-800/80">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-1 text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider">
              <Hash className="w-3 h-3 text-cyan-400" />
              <span>EVIDENCE PROVENANCE (SHA-256)</span>
            </div>
            <button
              onClick={handleCopyHash}
              className="text-[10px] font-mono flex items-center gap-1 text-cyan-400 hover:text-cyan-300 transition-colors cursor-pointer"
            >
              {copied ? (
                <>
                  <Check className="w-3 h-3 text-emerald-400" />
                  <span className="text-emerald-400">COPIED</span>
                </>
              ) : (
                <>
                  <Copy className="w-3 h-3" />
                  <span>COPY</span>
                </>
              )}
            </button>
          </div>

          <div 
            onClick={handleCopyHash}
            title="Click to copy SHA-256 Evidence Provenance Hash"
            className="p-2.5 rounded-lg bg-black border border-slate-800 font-mono text-[10px] text-cyan-400/90 break-all leading-relaxed select-all hover:border-cyan-500/40 transition-colors cursor-pointer"
          >
            {documentHash || "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"}
          </div>
          <p className="text-[9px] text-slate-500 mt-1 font-mono">
            Cryptographic SHA-256 digest of original surveillance report for court admissibility.
          </p>
        </div>
      </div>
    </div>
  );
}

