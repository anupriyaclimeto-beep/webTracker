import React, { useEffect, useState } from 'react';
import { Activity, Clock, Database, Globe, RefreshCw, ArrowRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';

export default function Overview() {
  const [portals, setPortals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const navigate = useNavigate();

  const fetchPortals = async () => {
    try {
      const res = await fetch(API_ENDPOINTS.portals);
      const data = await res.json();
      if (data.portals) setPortals(data.portals);
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
    setRefreshing(false);
  };

  useEffect(() => {
    fetchPortals();
  }, []);

  const handleRefresh = () => {
    setRefreshing(true);
    fetchPortals();
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[50vh] space-y-4">
        <RefreshCw className="w-10 h-10 text-blue-500 animate-spin" />
        <span className="text-slate-500 font-medium">Assembling live status metrics...</span>
      </div>
    );
  }

  const totalChanges = portals.reduce((acc, p) => acc + (p.total_changes || 0), 0);
  const portalsOffline = portals.filter(p => p.last_status === 'server_down' || p.last_status === 'error').length;

  return (
    <div className="space-y-8 animate-fadeIn">
      {/* Title / Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h1 className="text-3xl font-extrabold text-slate-900 tracking-tight">System Overview</h1>
          <p className="text-slate-500 text-sm mt-1">Real-time status monitoring and compliance log tracking.</p>
        </div>
        <button 
          onClick={handleRefresh}
          disabled={refreshing}
          className="inline-flex items-center px-4 py-2 bg-white border border-slate-200 hover:border-slate-300 text-slate-700 hover:text-slate-900 text-sm font-semibold rounded-xl transition shadow-sm hover:shadow-md disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 mr-2 ${refreshing ? 'animate-spin' : ''}`} />
          {refreshing ? 'Refreshing...' : 'Refresh Status'}
        </button>
      </div>

      {/* Hero Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        
        {/* Card 1: Tracked Portals */}
        <div className="relative overflow-hidden bg-gradient-to-br from-blue-600 via-indigo-600 to-indigo-700 rounded-2xl p-6 text-white shadow-lg shadow-indigo-100 flex flex-col justify-between min-h-[160px] group transition hover:scale-[1.01]">
          <div className="absolute right-0 bottom-0 opacity-10 transform translate-x-4 translate-y-4 group-hover:scale-110 transition duration-300">
            <Globe className="w-40 h-40" />
          </div>
          <div className="flex justify-between items-start">
            <div>
              <p className="text-indigo-100 font-semibold text-sm uppercase tracking-wider">Tracked Portals</p>
              <h3 className="text-5xl font-black mt-2 tracking-tight">{portals.length}</h3>
            </div>
            <span className="p-3 bg-white/10 rounded-xl backdrop-blur-md">
              <Globe className="w-6 h-6" />
            </span>
          </div>
          <div className="mt-4 pt-3 border-t border-white/10 flex items-center justify-between text-xs text-indigo-100">
            <span>{portalsOffline > 0 ? `${portalsOffline} portal${portalsOffline > 1 ? 's' : ''} responding slow` : "All connections online"}</span>
            <span className={`w-2 h-2 rounded-full ${portalsOffline > 0 ? 'bg-amber-400' : 'bg-emerald-400'} animate-ping`}></span>
          </div>
        </div>

        {/* Card 2: Total Changes */}
        <div className="relative overflow-hidden bg-gradient-to-br from-cyan-500 via-blue-600 to-blue-700 rounded-2xl p-6 text-white shadow-lg shadow-blue-100 flex flex-col justify-between min-h-[160px] group transition hover:scale-[1.01]">
          <div className="absolute right-0 bottom-0 opacity-10 transform translate-x-4 translate-y-4 group-hover:scale-110 transition duration-300">
            <Database className="w-40 h-40" />
          </div>
          <div className="flex justify-between items-start">
            <div>
              <p className="text-blue-100 font-semibold text-sm uppercase tracking-wider">Changes Detected</p>
              <h3 className="text-5xl font-black mt-2 tracking-tight">{totalChanges}</h3>
            </div>
            <span className="p-3 bg-white/10 rounded-xl backdrop-blur-md">
              <Database className="w-6 h-6" />
            </span>
          </div>
          <div className="mt-4 pt-3 border-t border-white/10 flex items-center justify-between text-xs text-blue-100 cursor-pointer" onClick={() => navigate('/changes')}>
            <span className="flex items-center hover:underline">
              View latest changes list <ArrowRight className="w-3.5 h-3.5 ml-1" />
            </span>
          </div>
        </div>

      </div>

      {/* Portal Status Section */}
      <div>
        <div className="flex justify-between items-center mb-6">
          <h2 className="text-xl font-bold text-slate-800 tracking-tight flex items-center">
            <Globe className="w-5 h-5 mr-2 text-slate-500" />
            Portal Connection Status
          </h2>
          <span className="text-xs text-slate-400 font-medium bg-slate-100 px-2.5 py-1 rounded-lg">
            Monitored: {portals.length} portals
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {portals.map((portal) => {
            const hasChanges = portal.total_changes > 0;
            const isOffline = portal.last_status === 'server_down' || portal.last_status === 'error';
            const isSlow = portal.last_status === 'slow';
            const isDone = portal.last_status === 'done' || portal.last_status === 'success';

            return (
              <div 
                key={portal.name} 
                onClick={() => navigate('/console', { state: { portal: portal.name } })}
                className="group relative bg-white rounded-2xl border border-slate-200 p-6 hover:shadow-xl hover:-translate-y-1 transition duration-300 ease-in-out cursor-pointer flex flex-col justify-between overflow-hidden"
              >
                {/* Visual indicator stripe */}
                <div className={`absolute top-0 left-0 right-0 h-1.5 ${
                  isOffline ? 'bg-gradient-to-r from-red-500 to-orange-500' :
                  isSlow ? 'bg-gradient-to-r from-amber-400 to-orange-400' :
                  isDone ? 'bg-gradient-to-r from-emerald-400 to-teal-500' :
                  'bg-slate-300'
                }`} />

                <div>
                  <div className="flex justify-between items-start gap-4 mb-4">
                    <h3 className="text-base font-extrabold text-slate-800 group-hover:text-blue-600 transition truncate max-w-[70%]">
                      {portal.name}
                    </h3>
                    
                    {/* Stylized Status Badge */}
                    <span className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold shadow-sm ${
                      isDone ? 'bg-emerald-50 text-emerald-700 border border-emerald-100' :
                      isSlow ? 'bg-amber-50 text-amber-800 border border-amber-100' :
                      isOffline ? 'bg-red-50 text-red-700 border border-red-100' :
                      'bg-slate-50 text-slate-600 border border-slate-100'
                    }`}>
                      <span className={`w-1.5 h-1.5 rounded-full mr-1.5 ${
                        isDone ? 'bg-emerald-500' :
                        isSlow ? 'bg-amber-500' :
                        isOffline ? 'bg-red-500' : 'bg-slate-400'
                      }`}></span>
                      {portal.last_status === 'server_down' ? 'Offline' :
                       portal.last_status === 'slow' ? 'Slow Response' :
                       portal.last_status === 'done' ? 'Healthy' :
                       portal.last_status || 'Stopped'}
                    </span>
                  </div>

                  {/* Body stats block */}
                  <div className="grid grid-cols-2 gap-4 py-3 bg-slate-50/50 rounded-xl border border-slate-100 p-4 mb-4">
                    <div className="flex flex-col">
                      <span className="text-xs text-slate-400 font-semibold uppercase">Changes</span>
                      <span className={`text-xl font-extrabold mt-0.5 ${hasChanges ? 'text-blue-600' : 'text-slate-800'}`}>
                        {portal.total_changes}
                      </span>
                    </div>
                    
                    <div className="flex flex-col">
                      <span className="text-xs text-slate-400 font-semibold uppercase">Last Run</span>
                      <span className="text-xs font-bold text-slate-700 mt-1 truncate">
                        {portal.last_crawl_at ? new Date(portal.last_crawl_at).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : 'Never'}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Card footer details / actions */}
                <div className="flex justify-between items-center text-xs text-slate-400 pt-2 border-t border-slate-100">
                  <span className="flex items-center font-medium">
                    <Clock className="w-3.5 h-3.5 mr-1" />
                    {portal.last_crawl_at ? new Date(portal.last_crawl_at).toLocaleDateString() : 'No run recorded'}
                  </span>
                  <span className="text-blue-500 group-hover:translate-x-1 transition flex items-center font-bold">
                    Console <ArrowRight className="w-3.5 h-3.5 ml-1" />
                  </span>
                </div>

              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
