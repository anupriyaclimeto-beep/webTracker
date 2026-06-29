import React, { useEffect, useState, useRef } from 'react';
import { Play, Square, Terminal } from 'lucide-react';
import { useLocation } from 'react-router-dom';
import { API_ENDPOINTS } from '../config';

export default function Console() {
  const location = useLocation();
  const [logs, setLogs] = useState('');
  const [isRunning, setIsRunning] = useState(false);
  const [status, setStatus] = useState('stopped');
  const [selectedPortal, setSelectedPortal] = useState(location.state?.portal || 'All Portals');
  const logEndRef = useRef(null);

  const fetchStatus = async () => {
    try {
      const res = await fetch(API_ENDPOINTS.crawlStatus);
      const data = await res.json();
      setIsRunning(data.running);
      setStatus(data.db_status || data.status || 'stopped');
      if (data.logs) {
        setLogs(data.logs);
      }
    } catch (err) {
      console.error("Status fetch error", err);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs]);

  const handleStart = async () => {
    try {
      await fetch(API_ENDPOINTS.crawlStart, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ portal: selectedPortal })
      });
      fetchStatus();
    } catch (err) {
      console.error(err);
    }
  };

  const handleStop = async () => {
    try {
      await fetch(API_ENDPOINTS.crawlStop, { method: 'POST' });
      fetchStatus();
    } catch (err) {
      console.error(err);
    }
  };

  return (
    <div className="space-y-6 flex flex-col h-[calc(100vh-8rem)]">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-bold text-slate-900 flex items-center">
          <Terminal className="w-6 h-6 mr-2 text-slate-700" />
          Crawler Console
        </h1>
        
        <div className="flex items-center space-x-4">
          <select 
            className="border border-slate-300 rounded-lg px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-blue-500 bg-white"
            value={selectedPortal}
            onChange={(e) => setSelectedPortal(e.target.value)}
            disabled={isRunning}
          >
            <option value="All Portals">All Portals</option>
            <option value="EPR PLASTIC">EPR PLASTIC</option>
            <option value="EPR BATTERY">Battery Portal</option>
            <option value="EPR EWASTE">E-Waste Portal</option>
            <option value="EPR ELV">ELV Portal</option>
            <option value="EPR TYRES">Tyre Portal</option>
            <option value="EPR USEDOIL">Used Oil Portal</option>
            <option value="EPR SSO">EPR SSO</option>
            <option value="MOEF">MOEF Portal</option>
            <option value="CPCB NIC">CPCB NIC</option>
            <option value="BEE RCO">BEE RCO</option>
          </select>

          {!isRunning ? (
            <button 
              onClick={handleStart}
              disabled={window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1'}
              className={`inline-flex items-center px-4 py-2 text-sm font-medium rounded-lg transition shadow-sm ${
                (window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1')
                  ? 'bg-slate-300 text-slate-500 cursor-not-allowed'
                  : 'bg-emerald-600 hover:bg-emerald-700 text-white'
              }`}
              title={(window.location.hostname !== 'localhost' && window.location.hostname !== '127.0.0.1') ? "Manual execution is disabled on the live server" : ""}
            >
              <Play className="w-4 h-4 mr-2" />
              Start Crawler
            </button>
          ) : (
            <button 
              onClick={handleStop}
              className="inline-flex items-center px-4 py-2 bg-red-600 hover:bg-red-700 text-white text-sm font-medium rounded-lg transition shadow-sm"
            >
              <Square className="w-4 h-4 mr-2" />
              Stop Crawler
            </button>
          )}
        </div>
      </div>

      <div className="flex-1 bg-slate-900 rounded-xl overflow-hidden flex flex-col shadow-inner border border-slate-800">
        <div className="bg-slate-800 px-4 py-2 flex items-center border-b border-slate-700">
          <div className="flex space-x-2">
            <div className="w-3 h-3 rounded-full bg-red-500"></div>
            <div className="w-3 h-3 rounded-full bg-yellow-500"></div>
            <div className="w-3 h-3 rounded-full bg-green-500"></div>
          </div>
          <span className="ml-4 text-xs font-medium text-slate-400 font-mono">crawler.log</span>
          {(isRunning || ['slow', 'server_down', 'error', 'aborted'].includes(status)) && (
            <span className={`ml-auto text-xs font-medium flex items-center ${
              status === 'slow' ? 'text-yellow-400' : 
              status === 'server_down' ? 'text-orange-400' :
              (status === 'error' || status === 'aborted') ? 'text-red-400' : 
              'text-emerald-400'
            }`}>
              <span className={`w-2 h-2 rounded-full mr-2 ${isRunning ? 'animate-pulse' : ''} ${
                status === 'slow' ? 'bg-yellow-400' : 
                status === 'server_down' ? 'bg-orange-400' :
                (status === 'error' || status === 'aborted') ? 'bg-red-400' : 
                'bg-emerald-400'
              }`}></span>
              {status === 'slow' ? 'Responding Slow...' : 
               status === 'server_down' ? 'Server Down' :
               status === 'error' ? 'Error' : 
               status === 'aborted' ? 'Aborted' : 'Running'}
            </span>
          )}
        </div>
        <div className="flex-1 p-4 overflow-y-auto font-mono text-sm text-slate-300 whitespace-pre-wrap">
          {logs || 'Ready to start...'}
          <div ref={logEndRef} />
        </div>
      </div>
    </div>
  );
}
