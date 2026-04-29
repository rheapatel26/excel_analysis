import React, { useState } from 'react';
import axios from 'axios';
import { 
  Activity, 
  AlertTriangle, 
  FileText, 
  Upload, 
  Download, 
  Zap,
  MessageSquare,
  ShieldCheck
} from 'lucide-react';

import {
  Chart as ChartJS,
  ArcElement,
  Tooltip,
  Legend,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
} from 'chart.js';

import Header from './components/Header';
import TabButton from './components/TabButton';
import OverviewTab from './components/OverviewTab';
import FraudTab from './components/FraudTab';
import DetailsTab from './components/DetailsTab';
import DataChatTab from './components/DataChatTab';
import PolicyAITab from './components/PolicyAITab';
import type { AnalysisData } from './types';

ChartJS.register(
  ArcElement,
  Tooltip,
  Legend,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title
);

const API_BASE = 'http://127.0.0.1:5001';

export default function App() {
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState(0);
  const [data, setData] = useState<AnalysisData | null>(null);
  const [activeTab, setActiveTab] = useState('overview');

  const [isRestoring, setIsRestoring] = useState(false);
  const [samples, setSamples] = useState<any[]>([]);

  // Load samples on mount
  React.useEffect(() => {
    const fetchSamples = async () => {
      try {
        const res = await axios.get(`${API_BASE}/api/sample`);
        setSamples(res.data.files || []);
      } catch (e) {
        console.error("Failed to load samples", e);
      }
    };
    fetchSamples();
  }, []);

  const steps = isRestoring 
    ? [
        'Connecting to Supabase Cloud...',
        'Checking Integrity Cache...',
        'Restoring Analytical State...',
        'Finalizing Dashboard View...'
      ]
    : [
        'Reading Claim Report...',
        'Mapping Alkem Headers...',
        'Validating Incurred Amounts...',
        'Scanning for Anomalies...',
        'Finalizing Executive Dashboard...'
      ];

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      analyzeFile(selectedFile);
    }
  };

  const analyzeFile = async (selectedFile: File) => {
    setLoading(true);
    setIsRestoring(false);
    setProgress(10);
    setCurrentStep(0);
    
    const interval = setInterval(() => {
      setCurrentStep(prev => (prev < 4 ? prev + 1 : prev));
      setProgress(prev => (prev < 90 ? prev + 20 : prev));
    }, 1200);

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      const res = await axios.post(`${API_BASE}/api/analyze`, formData);
      clearInterval(interval);
      setProgress(100);
      setTimeout(() => {
        setData(res.data);
        localStorage.setItem('activeFile', selectedFile.name);
        setLoading(false);
      }, 500);
    } catch (err: any) {
      clearInterval(interval);
      const msg = err.response?.data?.error || err.message || 'Connection failed';
      alert(`Analysis failed: ${msg}. Please ensure the Python server is running.`);
      setLoading(false);
    }
  };
  
  const analyzeSample = async (filename: string) => {
    setLoading(true);
    setIsRestoring(true);
    setProgress(20);
    setCurrentStep(0);
    try {
      const res = await axios.get(`${API_BASE}/api/sample/analyze/${filename}`);
      setProgress(100);
      setTimeout(() => {
        setData(res.data);
        localStorage.setItem('activeFile', filename);
        setLoading(false);
      }, 500);
    } catch (err: any) {
      alert("Failed to analyze sample dataset.");
      setLoading(false);
    }
  };

  // NEW: Session Restoration on Reload
  React.useEffect(() => {
    const savedFile = localStorage.getItem('activeFile');
    if (savedFile && !data) {
      const restoreSession = async () => {
        setLoading(true);
        setIsRestoring(true);
        setCurrentStep(0);
        setProgress(30);
        try {
          const res = await axios.post(`${API_BASE}/api/restore`, { file: savedFile });
          setProgress(100);
          setTimeout(() => {
            setData(res.data);
            setLoading(false);
          }, 500);
        } catch (e) {
          console.error("Session restore failed", e);
          localStorage.removeItem('activeFile');
        } finally {
          setLoading(false);
        }
      };
      restoreSession();
    }
  }, []);

  const handleExportAudit = async () => {
    if (!file) {
      alert('Original file not found. Please upload again.');
      return;
    }
    
    setExporting(true);
    const formData = new FormData();
    formData.append('file', file);
    
    try {
      const res = await axios.post(`${API_BASE}/api/download-ppt`, formData, {
        responseType: 'blob'
      });
      
      const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.presentationml.presentation' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      
      const contentDisposition = res.headers['content-disposition'];
      let filename = 'Audit_Report.pptx';
      if (contentDisposition) {
        const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/);
        if (filenameMatch && filenameMatch.length === 2) {
          filename = filenameMatch[1];
        }
      } else if (file.name) {
        filename = `${file.name.split('.')[0]}_Report.pptx`;
      }
      
      link.setAttribute('download', filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (err: any) {
      console.error('Export failed', err);
      alert('Failed to export audit report.');
    } finally {
      setExporting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center p-8 bg-white">
        <div className="relative w-20 h-20 mb-12">
          <div className="absolute inset-0 border-4 border-slate-50 rounded-full"></div>
          <div className="absolute inset-0 border-4 border-t-[#0068B1] rounded-full animate-spin"></div>
        </div>
        <div className="w-full max-w-md h-2 bg-slate-50 rounded-full overflow-hidden mb-10">
          <div 
            className="h-full bg-gradient-to-r from-[#0068B1] to-[#E4232B] transition-all duration-700" 
            style={{ width: `${progress}%` }}
          ></div>
        </div>
        <div className="space-y-4 text-center">
          {steps.map((step, i) => (
            <div key={i} className={`flex items-center justify-center gap-3 text-lg font-bold transition-all duration-300 ${i === currentStep ? 'text-[#0068B1] scale-105' : 'text-slate-300 opacity-50'}`}>
              {i === currentStep ? <Zap className="w-5 h-5 animate-pulse" /> : <div className="w-5" />}
              {step}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (data) {
    return (
      <div className="min-h-screen bg-slate-50/50 pb-20">
        <Header />
        <main className="max-w-[1600px] mx-auto px-8 py-10">
          <div className="flex justify-between items-center mb-10 fade-up">
            <div className="flex items-center gap-6">
              <div className="p-4 bg-white rounded-3xl shadow-sm border border-slate-100">
                <img src="/assets/logo_circular.png" className="w-14 h-14" alt="Icon" />
              </div>
              <div>
                <h1 className="text-3xl font-black text-[#001D4A] tracking-tight">{data.file}</h1>
                <div className="flex items-center gap-4 mt-2">
                  <span className="text-sm text-slate-500 font-bold uppercase tracking-wider">Institutional Audit Mode</span>
                  <div className="w-1.5 h-1.5 rounded-full bg-slate-300" />
                  <span className="text-sm text-slate-500 font-medium">Processed {data.kpis.total_claims} records</span>
                </div>
              </div>
            </div>
            
            <div className="flex gap-4">
               <button 
                onClick={() => { setData(null); setFile(null); }}
                className="px-6 py-3 rounded-xl border border-slate-200 bg-white text-[#001D4A] font-bold hover:bg-slate-50 transition-all flex items-center gap-2"
              >
                <Upload size={18} /> New Report
              </button>
              <button 
                onClick={handleExportAudit}
                disabled={exporting}
                className="btn-primary flex items-center gap-2 disabled:opacity-70 disabled:cursor-not-allowed"
              >
                <Download size={18} /> {exporting ? 'Exporting...' : 'Export Audit'}
              </button>
            </div>
          </div>

          <div className="flex gap-10 mb-10 border-b border-slate-200 fade-up">
            <TabButton active={activeTab === 'overview'} onClick={() => setActiveTab('overview')} icon={<Activity size={18} />} label="Overview" />
            <TabButton active={activeTab === 'data chat'} onClick={() => setActiveTab('data chat')} icon={<MessageSquare size={18} />} label="Data Chat" />
            <TabButton active={activeTab === 'policy ai'} onClick={() => setActiveTab('policy ai')} icon={<ShieldCheck size={18} />} label="Policy AI" />
            <TabButton active={activeTab === 'fraud & outliers'} onClick={() => setActiveTab('fraud & outliers')} icon={<AlertTriangle size={18} />} label="Intelligence" />
            <TabButton active={activeTab === 'full details'} onClick={() => setActiveTab('full details')} icon={<FileText size={18} />} label="Full Ledger" />
          </div>

          <div className="fade-up">
            {activeTab === 'overview' && <OverviewTab data={data} />}
            {activeTab === 'data chat' && <DataChatTab data={data} />}
            {activeTab === 'policy ai' && <PolicyAITab />}
            {activeTab === 'fraud & outliers' && <FraudTab data={data} />}
            {activeTab === 'full details' && <DetailsTab data={data} />}
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-white overflow-hidden font-inter">
      <Header />
      <div className="relative max-w-5xl mx-auto pt-32 pb-24 px-8 text-center fade-up z-10">
        <div className="inline-flex items-center gap-3 px-6 py-3 rounded-full bg-blue-50 border border-blue-100 mb-12">
          <div className="w-2 h-2 rounded-full bg-[#0068B1] animate-pulse" />
          <span className="text-[10px] font-black tracking-[0.2em] text-[#0068B1] uppercase">Agentic Claim Intelligence Active</span>
        </div>
        
        <h1 className="text-8xl font-black text-[#001D4A] tracking-tighter mb-8 leading-[0.9]">
          Institutional Claim<br /><span className="text-[#0068B1]">Analysis, Instantly.</span>
        </h1>
        
        <p className="text-xl text-slate-500 mb-16 max-w-2xl mx-auto leading-relaxed font-medium">
          Get institutional-grade insights, fraud signals, and executive narratives from your claim data in seconds.
        </p>

        <label className="block w-full max-w-3xl mx-auto group cursor-pointer">
          <div className="relative border-2 border-dashed border-slate-200 rounded-[40px] p-24 transition-all group-hover:border-[#0068B1] group-hover:bg-blue-50/30">
            <Upload className="w-16 h-16 text-slate-300 mx-auto mb-8 group-hover:text-[#0068B1] group-hover:scale-110 transition-all duration-500" />
            <div className="text-2xl font-bold text-[#001D4A] mb-3">Drop your MIS file here or <span className="text-[#0068B1]">browse</span></div>
            <p className="text-sm text-slate-400 font-semibold tracking-wide">Supports institutional formats: .xlsx, .xlsb, .xls, .csv</p>
          </div>
          <input type="file" className="hidden" onChange={handleFileUpload} accept=".xlsx,.xlsb,.xls,.csv" />
        </label>

        {samples.length > 0 && (
          <div className="mt-16 max-w-4xl mx-auto">
            <h3 className="text-xs font-black uppercase tracking-[0.3em] text-slate-400 mb-8">Quick Start with Sample Datasets</h3>
            <div className="grid grid-cols-3 gap-4">
              {samples.map((s, i) => (
                <button 
                  key={i}
                  onClick={() => analyzeSample(s.file)}
                  className="p-5 rounded-2xl border border-slate-100 bg-white shadow-sm hover:shadow-md hover:border-blue-200 transition-all text-left group"
                >
                  <div className="flex items-center gap-3 mb-3">
                    <div className="p-2 bg-blue-50 text-blue-600 rounded-lg group-hover:bg-[#001D4A] group-hover:text-white transition-all">
                      <FileSpreadsheet size={16} />
                    </div>
                    <span className="text-[10px] font-black uppercase tracking-wider text-[#0068B1]">{s.file.split('.').pop()}</span>
                  </div>
                  <div className="text-sm font-bold text-[#001D4A] truncate mb-1">{s.file.split('_').pop()?.replace('.xlsb', '').replace('.xlsx', '') || s.file}</div>
                  <div className="text-[10px] text-slate-400 font-bold uppercase tracking-widest">{(s.size / 1024).toFixed(0)} KB • Institutional</div>
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <img src="/assets/logo_circular.png" className="fixed bottom-[-10%] right-[-5%] w-[600px] h-[600px] opacity-[0.03] pointer-events-none" alt="BG" />
    </div>
  );
}
