import React, { useEffect, useState } from 'react';
import { ExternalLink, Filter, Eye, Image as ImageIcon, X, Globe, FileText, ZoomIn, ZoomOut, RefreshCw } from 'lucide-react';
import { API_ENDPOINTS } from '../config';

function ChangeCard({ change, onImageClick }) {
  // Check if we have a diff image URL
  const hasDiffImage = !!change.diff_detail?.diff_image_url;
  const [activeView, setActiveView] = useState(hasDiffImage ? 'diff' : 'screenshot');

  const imageUrl = activeView === 'diff' 
    ? change.diff_detail?.diff_image_url 
    : change.screenshot_url;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm flex flex-col md:flex-row gap-6">
      {/* Details Column */}
      <div className="flex-1 flex flex-col justify-between space-y-4">
        <div>
          <div className="flex flex-wrap justify-between items-start gap-2 mb-2">
            <div>
              <h3 className="text-lg font-bold text-slate-800">{change.portal}</h3>
              <div className="flex items-center space-x-2 mt-1">
                <span className="inline-block px-2.5 py-0.5 bg-blue-50 text-blue-700 text-xs font-semibold rounded-full uppercase">
                  {change.diff_type}
                </span>
                {hasDiffImage && (
                  <span className="inline-block px-2.5 py-0.5 bg-emerald-50 text-emerald-700 text-xs font-semibold rounded-full">
                    Visual Diff Highlight
                  </span>
                )}
              </div>
            </div>
            <div className="text-sm text-slate-500">
              {new Date(change.timestamp).toLocaleString()}
            </div>
          </div>
          
          {/* AI / Content Summary */}
          {(() => {
            const aiSummary = change.ai_summary || (change.diff_detail && change.diff_detail.summary) || "";
            const txt = (aiSummary || "").toString();
            const lower = txt.toLowerCase();
            const show = txt.trim() && !lower.includes("no description") && !lower.includes("no visible") && !lower.includes("no changes");
            if (!show) return null;
            
            // Check if it's the raw formatted diff string
            if (txt.includes("Added:") || txt.includes("Removed:")) {
              const parts = txt.split("|");
              return (
                <div className="space-y-3 my-3">
                  {parts.map((part, i) => {
                    const p = part.trim();
                    if (p.startsWith("Added:")) {
                      const items = p.replace("Added:", "").split(",").map(s => s.trim().replace(/^"|"$/g, ''));
                      return (
                        <div key={i} className="bg-emerald-50/50 border border-emerald-100 rounded-lg p-3">
                          <span className="text-emerald-700 text-xs font-bold uppercase tracking-wider mb-2 block">Data Added / New Items</span>
                          <div className="flex flex-wrap gap-2">
                            {items.map((item, idx) => (
                              item ? <span key={idx} className="bg-white border border-emerald-200 text-emerald-800 text-xs px-2.5 py-1 rounded-md shadow-sm font-medium">{item}</span> : null
                            ))}
                          </div>
                        </div>
                      );
                    } else if (p.startsWith("Removed:")) {
                      const items = p.replace("Removed:", "").split(",").map(s => s.trim().replace(/^"|"$/g, ''));
                      return (
                        <div key={i} className="bg-rose-50/50 border border-rose-100 rounded-lg p-3">
                          <span className="text-rose-700 text-xs font-bold uppercase tracking-wider mb-2 block">Data Removed / Deleted Items</span>
                          <div className="flex flex-wrap gap-2">
                            {items.map((item, idx) => (
                              item ? <span key={idx} className="bg-white border border-rose-200 text-rose-800 text-xs px-2.5 py-1 rounded-md shadow-sm font-medium line-through decoration-rose-300">{item}</span> : null
                            ))}
                          </div>
                        </div>
                      );
                    }
                    return <p key={i} className="text-slate-700 text-sm">{p}</p>;
                  })}
                </div>
              );
            }

            return (
              <div className="bg-slate-50 rounded-lg p-4 border border-slate-100 my-3">
                <p className="text-slate-700 text-sm whitespace-pre-wrap leading-relaxed">
                  {txt}
                </p>
              </div>
            );
          })()}
        </div>

        {/* Action Links & Metadata */}
        <div className="space-y-3 pt-2 border-t border-slate-100">
          <div className="flex items-center text-xs text-slate-500 max-w-full overflow-hidden truncate">
            <Globe className="w-3.5 h-3.5 mr-1.5 flex-shrink-0" />
            <span className="truncate">{change.url}</span>
          </div>

          <div className="flex flex-wrap gap-2">
            {change.url && (
              <a 
                href={change.url} 
                target="_blank" 
                rel="noopener noreferrer"
                className="inline-flex items-center px-3 py-1.5 border border-slate-200 text-xs font-medium rounded-lg text-slate-700 bg-white hover:bg-slate-50 transition shadow-sm"
              >
                <Globe className="w-3.5 h-3.5 mr-1.5" />
                Live Page
                <ExternalLink className="w-3 h-3 ml-1" />
              </a>
            )}
            {change.html_url && (
              <a 
                href={change.html_url} 
                target="_blank" 
                rel="noopener noreferrer"
                className="inline-flex items-center px-3 py-1.5 border border-blue-200 text-xs font-medium rounded-lg text-blue-700 bg-blue-50/50 hover:bg-blue-50 transition shadow-sm"
              >
                <FileText className="w-3.5 h-3.5 mr-1.5" />
                View Captured HTML
                <ExternalLink className="w-3 h-3 ml-1" />
              </a>
            )}
          </div>
        </div>
      </div>

      {/* Screenshot / Visuals Column */}
      <div className="w-full md:w-80 flex-shrink-0 flex flex-col space-y-2">
        {imageUrl ? (
          <>
            <div className="flex justify-between items-center bg-slate-100 p-1 rounded-lg">
              <button
                onClick={() => setActiveView('screenshot')}
                className={`flex-1 text-center py-1 text-xs font-medium rounded-md transition ${
                  activeView === 'screenshot' 
                    ? 'bg-white text-slate-800 shadow-sm' 
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                Screenshot
              </button>
              {hasDiffImage && (
                <button
                  onClick={() => setActiveView('diff')}
                  className={`flex-1 text-center py-1 text-xs font-medium rounded-md transition ${
                    activeView === 'diff' 
                      ? 'bg-white text-slate-800 shadow-sm' 
                      : 'text-slate-500 hover:text-slate-700'
                  }`}
                >
                  Diff Highlight
                </button>
              )}
            </div>

            <div 
              onClick={() => onImageClick(imageUrl)}
              className="relative group aspect-[16/10] md:h-48 rounded-lg overflow-hidden border border-slate-200 cursor-zoom-in bg-slate-50 flex items-center justify-center shadow-inner"
            >
              <img 
                src={imageUrl} 
                alt="Change Visual" 
                className="w-full h-full object-cover object-top transition group-hover:scale-105 duration-200"
              />
              <div className="absolute inset-0 bg-black/40 opacity-0 group-hover:opacity-100 flex items-center justify-center transition duration-200">
                <span className="inline-flex items-center px-2.5 py-1.5 bg-black/60 rounded-md text-white text-xs font-medium shadow-lg">
                  <Eye className="w-3.5 h-3.5 mr-1.5" />
                  View Full Size
                </span>
              </div>
            </div>
          </>
        ) : (
          <div className="aspect-[16/10] md:h-48 rounded-lg border border-dashed border-slate-300 flex flex-col items-center justify-center bg-slate-50 text-slate-400">
            <ImageIcon className="w-8 h-8 mb-2 stroke-[1.5]" />
            <span className="text-xs">No screenshot captured</span>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Changes() {
  const [changes, setChanges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterPortal, setFilterPortal] = useState('');
  const [filterDate, setFilterDate] = useState('');
  const [selectedImage, setSelectedImage] = useState(null);
  const [zoom, setZoom] = useState(1);

  useEffect(() => {
    if (!selectedImage) setZoom(1);
  }, [selectedImage]);

  const fetchChanges = async (portal = '') => {
    setLoading(true);
    try {
      const url = portal ? `${API_ENDPOINTS.changes}/${encodeURIComponent(portal)}` : API_ENDPOINTS.changes;
      const res = await fetch(url);
      const data = await res.json();
      // Filter out changes that are "no visible" / noise-only so cards don't show
      const raw = data.changes || [];
      function parseDetail(change) {
        let d = change.diff_detail || {};
        if (typeof d === 'string' && d) {
          try { d = JSON.parse(d); } catch (e) { d = {}; }
        }
        return d || {};
      }
      function isVisible(change) {
        const d = parseDetail(change);
        const type = (change.diff_type || "").toLowerCase();
        const ai = (change.ai_summary || (d.summary || "") || "").toString().toLowerCase();
        if (ai.includes("no description") || ai.includes("no visible") || ai.includes("no changes")) return false;
        if (type === "visual") {
          const pixels = Number(d.changed_pixels || 0);
          const ratio = Number(d.change_ratio || 0);
          return pixels > 0 && ratio > 0.05;
        }
        if (type === "html") {
          const words = Number(d.words_changed || d.wordsChanged || 0);
          const lines = Number(d.diff_lines || d.lines_changed || 0);
          const highlighted = Array.isArray(d.highlighted_lines) ? d.highlighted_lines.length > 0 : false;
          if (words === 0 && lines === 0 && !highlighted) return false;
          return true;
        }
        if (type === "har" || type === "json") {
          // treat non-empty diff detail as visible
          if (Object.keys(d).length === 0) return false;
          if (type === "har") {
            const new_ep = d.new_endpoints || [];
            const rem_ep = d.removed_endpoints || [];
            return (Array.isArray(new_ep) && new_ep.length>0) || (Array.isArray(rem_ep) && rem_ep.length>0);
          }
          return true;
        }
        // default: show
        return true;
      }
      const visible = raw.filter(isVisible);
      setChanges(visible);
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  useEffect(() => {
    fetchChanges(filterPortal);
  }, [filterPortal]);

  const filteredChanges = changes.filter(change => {
    if (!filterDate) return true;
    const changeDate = new Date(change.timestamp).toISOString().split('T')[0];
    return changeDate === filterDate;
  });

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center flex-wrap gap-4">
        <h1 className="text-2xl font-bold text-slate-900">Latest Changes</h1>
        <div className="flex items-center space-x-2 flex-wrap gap-y-2">
          <Filter className="w-4 h-4 text-slate-500 hidden sm:block" />
          
          <input 
            type="date" 
            className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-blue-500"
            value={filterDate}
            onChange={(e) => setFilterDate(e.target.value)}
            title="Filter by date"
          />

          <select 
            className="border border-slate-300 rounded-lg px-3 py-1.5 text-sm outline-none focus:ring-2 focus:ring-blue-500"
            value={filterPortal}
            onChange={(e) => setFilterPortal(e.target.value)}
          >
            <option value="">All Portals</option>
            <option value="EPR PLASTIC">EPR PLASTIC</option>
            <option value="EPR BATTERY">Battery Portal</option>
            <option value="EPR EWASTE">E-Waste Portal</option>
            <option value="EPR ELV">ELV Portal</option>
            <option value="EPR TYRES">Tyre Portal</option>
            <option value="EPR USEDOIL">Used Oil Portal</option>
          </select>
        </div>
      </div>

      {loading ? (
        <div className="text-center py-12 text-slate-500 animate-pulse">Loading changes...</div>
      ) : filteredChanges.length === 0 ? (
        <div className="text-center py-12 text-slate-500 bg-white rounded-xl border border-slate-200">
          No changes found.
        </div>
      ) : (
        <div className="space-y-4">
          {filteredChanges.map((change) => (
            <ChangeCard 
              key={change.id} 
              change={change} 
              onImageClick={(url) => setSelectedImage(url)} 
            />
          ))}
        </div>
      )}

      {/* Lightbox / Modal for full-size screenshot */}
      {selectedImage && (
        <div 
          className="fixed inset-0 bg-black/90 z-50 flex flex-col items-center justify-center p-4 animate-fadeIn"
          onClick={() => setSelectedImage(null)}
        >
          {/* Controls Bar */}
          <div 
            className="absolute top-4 right-4 flex space-x-2 z-50 bg-slate-800/80 backdrop-blur-sm p-1.5 rounded-full shadow-lg border border-slate-700/50"
            onClick={(e) => e.stopPropagation()}
          >
            <button 
              className="p-2 hover:bg-slate-700 rounded-full text-slate-300 hover:text-white transition"
              title="Zoom Out"
              onClick={() => setZoom(z => Math.max(0.5, z - 0.25))}
            >
              <ZoomOut className="w-5 h-5" />
            </button>
            <div className="flex items-center px-2 text-sm font-mono text-slate-300 font-medium">
              {Math.round(zoom * 100)}%
            </div>
            <button 
              className="p-2 hover:bg-slate-700 rounded-full text-slate-300 hover:text-white transition"
              title="Zoom In"
              onClick={() => setZoom(z => Math.min(4, z + 0.25))}
            >
              <ZoomIn className="w-5 h-5" />
            </button>
            <div className="w-px h-6 bg-slate-600/50 self-center mx-1"></div>
            <button 
              className="p-2 hover:bg-slate-700 rounded-full text-slate-300 hover:text-white transition"
              title="Reset Zoom"
              onClick={() => setZoom(1)}
            >
              <RefreshCw className="w-5 h-5" />
            </button>
            <div className="w-px h-6 bg-slate-600/50 self-center mx-1"></div>
            <button 
              className="p-2 hover:bg-red-500/20 rounded-full text-slate-300 hover:text-red-400 transition"
              title="Close"
              onClick={() => setSelectedImage(null)}
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div 
            className={`relative w-full h-full overflow-auto flex ${zoom > 1 ? 'items-start justify-start' : 'items-center justify-center'} p-8`}
            onClick={(e) => e.stopPropagation()}
          >
            <img 
              src={selectedImage} 
              alt="Enlarged screenshot" 
              className="rounded-lg shadow-2xl transition-all duration-200"
              style={{
                width: zoom > 1 ? `${zoom * 100}%` : 'auto',
                maxWidth: zoom === 1 ? '100%' : 'none',
                maxHeight: zoom === 1 ? '85vh' : 'none',
                objectFit: 'contain'
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
