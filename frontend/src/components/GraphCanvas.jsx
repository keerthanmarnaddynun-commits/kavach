import React, { useEffect, useRef } from 'react';
import cytoscape from 'cytoscape';
import { ZoomIn, ZoomOut, Maximize2, RefreshCw, Layers } from 'lucide-react';

export default function GraphCanvas({ elements, kingpinId, onSelectNode, selectedNodeId }) {
  const containerRef = useRef(null);
  const cyRef = useRef(null);

  useEffect(() => {
    if (!containerRef.current) return;

    // Destroy any existing instance
    if (cyRef.current) {
      cyRef.current.destroy();
      cyRef.current = null;
    }

    if (!elements || (!elements.nodes && !elements.edges && !Array.isArray(elements))) {
      return;
    }

    const cy = cytoscape({
      container: containerRef.current,
      elements: elements,
      boxSelectionEnabled: false,
      autounselectify: false,
      style: [
        {
          selector: 'node',
          style: {
            'label': 'data(label)',
            'color': '#f8fafc',
            'font-size': '11px',
            'font-weight': '500',
            'text-valign': 'bottom',
            'text-margin-y': 7,
            'background-color': '#475569',
            'width': 38,
            'height': 38,
            'border-width': 3,
            'border-color': 'rgba(255, 255, 255, 0.15)',
            'text-background-color': '#000000',
            'text-background-opacity': 0.85,
            'text-background-padding': '3px',
            'text-background-shape': 'roundrectangle'
          }
        },
        // Orange for Persons with thick borders
        {
          selector: 'node[type = "PERSON"]',
          style: {
            'background-color': '#f59e0b',
            'border-color': '#d97706',
            'border-width': 3,
            'width': 44,
            'height': 44
          }
        },
        // Green for Phone Numbers with thick borders
        {
          selector: 'node[type = "PHONE"]',
          style: {
            'background-color': '#10b981',
            'border-color': '#059669',
            'border-width': 3,
            'width': 36,
            'height': 36
          }
        },
        // Cyan for Hardware / IMEI with thick borders
        {
          selector: 'node[type = "IMEI"]',
          style: {
            'background-color': '#06b6d4',
            'border-color': '#0891b2',
            'border-width': 3,
            'width': 34,
            'height': 34
          }
        },
        // Violet for Financial Accounts with thick borders
        {
          selector: 'node[type = "ACCOUNT"]',
          style: {
            'background-color': '#8b5cf6',
            'border-color': '#7c3aed',
            'border-width': 3,
            'width': 40,
            'height': 40
          }
        },
        // Kingpin Node: 64px, #ef4444 background, #facc15 border, heavy red glow shadow
        {
          selector: 'node[?isKingpin], node[id = "' + (kingpinId || '') + '"]',
          style: {
            'background-color': '#ef4444',
            'border-width': 4,
            'border-color': '#facc15',
            'width': 64,
            'height': 64,
            'font-size': '13px',
            'font-weight': '700',
            'color': '#fef08a',
            'shadow-blur': 25,
            'shadow-color': '#ef4444',
            'shadow-opacity': 0.85,
            'z-index': 999
          }
        },
        // Default Directed Edges
        {
          selector: 'edge',
          style: {
            'width': 2,
            'line-color': '#334155',
            'target-arrow-color': '#64748b',
            'target-arrow-shape': 'triangle',
            'arrow-scale': 1.15,
            'curve-style': 'bezier',
            'label': 'data(label)',
            'font-size': '9px',
            'color': '#94a3b8',
            'text-rotation': 'autorotate',
            'text-background-color': '#070b14',
            'text-background-opacity': 0.9,
            'text-background-padding': '2px'
          }
        },
        // Financial Transactions (Dashed Purple)
        {
          selector: 'edge[label *= "TRANSFER"], edge[label *= "FUNDS"]',
          style: {
            'line-color': '#8b5cf6',
            'target-arrow-color': '#8b5cf6',
            'line-style': 'dashed',
            'width': 2.5
          }
        },
        // Communication Links (Green)
        {
          selector: 'edge[label *= "COMMUNICAT"]',
          style: {
            'line-color': '#10b981',
            'target-arrow-color': '#10b981',
            'width': 2.5
          }
        },
        // Selected Highlight
        {
          selector: ':selected',
          style: {
            'border-width': 4,
            'border-color': '#38bdf8',
            'line-color': '#38bdf8',
            'target-arrow-color': '#38bdf8'
          }
        }
      ],
      layout: {
        name: 'cose',
        padding: 60,
        animate: true,
        animationDuration: 600,
        nodeRepulsion: 14000,
        idealEdgeLength: 130,
        edgeElasticity: 100
      }
    });

    // Handle node selection
    cy.on('tap', 'node', (evt) => {
      const node = evt.target;
      const data = node.data();
      const degree = node.degree();
      if (onSelectNode) {
        onSelectNode({ ...data, degree });
      }
    });

    // Clear selection on background tap
    cy.on('tap', (evt) => {
      if (evt.target === cy) {
        if (onSelectNode) onSelectNode(null);
      }
    });

    cyRef.current = cy;

    return () => {
      if (cyRef.current) {
        cyRef.current.destroy();
        cyRef.current = null;
      }
    };
  }, [elements, kingpinId]);

  // Synchronize external selection if selectedNodeId changes
  useEffect(() => {
    if (!cyRef.current) return;
    if (selectedNodeId) {
      const target = cyRef.current.getElementById(selectedNodeId);
      if (target.length) {
        cyRef.current.$(':selected').unselect();
        target.select();
      }
    }
  }, [selectedNodeId]);

  const handleFit = () => cyRef.current && cyRef.current.fit(50);
  const handleZoomIn = () => cyRef.current && cyRef.current.zoom(cyRef.current.zoom() * 1.25);
  const handleZoomOut = () => cyRef.current && cyRef.current.zoom(cyRef.current.zoom() * 0.8);
  const handleReset = () => {
    if (!cyRef.current) return;
    cyRef.current.layout({
      name: 'cose',
      padding: 60,
      animate: true,
      animationDuration: 500,
      nodeRepulsion: 14000,
      idealEdgeLength: 130
    }).run();
  };

  return (
    <div className="relative w-full h-full bg-gradient-to-br from-[#0c1427] via-[#050811] to-[#000000] overflow-hidden select-none">
      {/* Floating Tactical Canvas Controls */}
      <div className="absolute top-4 right-4 z-20 flex items-center gap-1.5 bg-slate-900/90 border border-slate-800 p-1.5 rounded-lg shadow-2xl backdrop-blur-md">
        <button
          onClick={handleFit}
          title="Fit Graph to Screen"
          className="p-1.5 rounded text-slate-400 hover:text-cyan-400 hover:bg-slate-800 transition-colors cursor-pointer"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
        <button
          onClick={handleZoomIn}
          title="Zoom In"
          className="p-1.5 rounded text-slate-400 hover:text-cyan-400 hover:bg-slate-800 transition-colors cursor-pointer"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={handleZoomOut}
          title="Zoom Out"
          className="p-1.5 rounded text-slate-400 hover:text-cyan-400 hover:bg-slate-800 transition-colors cursor-pointer"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <div className="h-4 w-[1px] bg-slate-700 mx-1" />
        <button
          onClick={handleReset}
          title="Re-run CoSE Physics Layout"
          className="flex items-center gap-1 px-2 py-1 rounded text-xs font-mono text-slate-300 hover:text-white hover:bg-slate-800 transition-colors cursor-pointer"
        >
          <RefreshCw className="w-3.5 h-3.5 text-cyan-400" />
          <span>RE-CENTER</span>
        </button>
      </div>

      {/* Cytoscape DOM container */}
      <div ref={containerRef} className="w-full h-full cursor-grab active:cursor-grabbing" />
    </div>
  );
}

