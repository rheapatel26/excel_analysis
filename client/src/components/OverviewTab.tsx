import { FileText, Activity, TrendingUp, Hospital, CheckCircle2, AlertTriangle, PieChart, Brain } from 'lucide-react';
import { Doughnut, Bar, Line } from 'react-chartjs-2';
import type { AnalysisData } from '../types';

function KPIBox({ title, value, sub, icon, accent, isAlert }: any) {
  return (
    <div className="bg-white p-7 rounded-[32px] border border-slate-100 shadow-sm group hover:shadow-xl hover:-translate-y-1 transition-all relative overflow-hidden">
      {accent && <div className="absolute top-0 left-0 w-full h-1" style={{ backgroundColor: accent }} />}
      <div className="flex justify-between items-center mb-6">
        <div className="p-3 bg-slate-50 rounded-2xl text-slate-400 group-hover:bg-blue-50 group-hover:text-[#0068B1] transition-all">
          {icon}
        </div>
        {isAlert && <div className="w-2 h-2 rounded-full bg-red-500 animate-ping" />}
      </div>
      <div className="text-[10px] font-black uppercase tracking-[0.2em] text-slate-400 mb-1">{title}</div>
      <div className="text-2xl font-black text-[#001D4A] mb-1 tracking-tight">{value}</div>
      <div className="text-[10px] font-bold text-slate-400">{sub}</div>
    </div>
  );
}

function ChartCard({ title, icon, children }: any) {
  return (
    <div className="bg-white p-10 rounded-[40px] border border-slate-100 shadow-sm">
      <div className="flex items-center gap-4 mb-10">
        <div className="p-3 bg-slate-50 rounded-2xl text-[#0068B1]">
          {icon}
        </div>
        <h3 className="text-lg font-bold text-[#001D4A]">{title}</h3>
      </div>
      {children}
    </div>
  );
}

export default function OverviewTab({ data }: { data: AnalysisData }) {
  const kpis = data.kpis;
  return (
    <div className="space-y-10">
      {/* 6-Column KPI Grid */}
      <div className="grid grid-cols-6 gap-6">
        <KPIBox title="Total Claims" value={kpis.total_claims.toLocaleString()} sub={`${kpis.total_claims} Records Processed`} icon={<FileText size={20} />} />
        <KPIBox title="Total Incurred" value={`\u20B9${(kpis.total_incurred / 10000000).toFixed(2)} Cr`} sub={`\u20B9${kpis.total_incurred.toLocaleString()} Total`} icon={<Activity size={20} />} accent="#0068B1" />
        <KPIBox title="Avg Claim" value={`\u20B9${kpis.avg_claim.toLocaleString(undefined, {maximumFractionDigits: 0})}`} sub={`Per ${data.kpis.total_claims} Units`} icon={<TrendingUp size={20} />} accent="#10B981" />
        <KPIBox title="Cashless %" value={`${kpis.cashless_pct}%`} sub={`${kpis.cashless_count} Cashless Claims`} icon={<Hospital size={20} />} accent="#6366F1" />
        <KPIBox title="Approval Rate" value={`${kpis.approval_rate}%`} sub={`${kpis.approved_count} Claims Approved`} icon={<CheckCircle2 size={20} />} accent="#22C55E" />
        <KPIBox title="Anomalies" value={data.fraud_flags.length} sub={`${data.fraud_flags.length} High-Risk Signals`} icon={<AlertTriangle size={20} />} accent="#EF4444" isAlert />
      </div>

      {/* AI Summary Card */}
      <div className="bg-white p-10 rounded-[40px] border border-slate-100 shadow-xl shadow-blue-900/5 relative overflow-hidden group">
        <div className="absolute top-0 right-0 p-12 opacity-[0.03] group-hover:opacity-[0.05] transition-opacity">
          <Brain size={180} className="text-[#0068B1]" />
        </div>
        <div className="flex justify-between items-center mb-8">
          <div className="flex items-center gap-4">
            <div className="w-1.5 h-6 bg-[#0068B1] rounded-full" />
            <h2 className="text-xs font-black uppercase tracking-[0.3em] text-[#0068B1]">AI Executive Narrative</h2>
          </div>
        </div>
        
        <div 
          className="text-xl font-medium leading-[1.8] text-[#001D4A] space-y-6"
          dangerouslySetInnerHTML={{ 
            __html: data.ai_narrative
              .replace(/\*\*(.*?)\*\*/g, '<span class="text-[#0068B1] font-bold">$1</span>') 
          }}
        />
      </div>

      {/* Charts Grid */}
      <div className="grid grid-cols-2 gap-8">
        <ChartCard title="Claim Type Distribution" icon={<PieChart size={18} />}>
          <div className="h-[350px] flex items-center justify-center">
            <Doughnut 
              data={{
                labels: ['CASHLESS', 'REIMBURSEMENT'],
                datasets: [{
                  data: [kpis.cashless_count, kpis.reimb_count],
                  backgroundColor: ['#0068B1', '#6366F1'],
                  borderWidth: 0,
                  hoverOffset: 20
                }]
              }}
              options={{ 
                plugins: { 
                  legend: { 
                    position: 'bottom',
                    labels: { color: '#64748B', padding: 20, font: { weight: 'bold', size: 10 } } 
                  } 
                },
                cutout: '75%'
              }}
            />
          </div>
        </ChartCard>

        <ChartCard title="Top Utilization Hospitals" icon={<Hospital size={18} />}>
           <Bar 
            data={{
              labels: data.hospital_breakdown.slice(0, 8).map((h: any) => h.hospital.substring(0, 15)),
              datasets: [{
                label: 'Incurred (\u20B9)',
                data: data.hospital_breakdown.slice(0, 8).map((h: any) => h.total_amt),
                backgroundColor: '#0068B1',
                borderRadius: 12,
              }]
            }}
            options={{ 
              scales: {
                y: { grid: { color: '#F1F5F9' }, ticks: { color: '#94A3B8' } },
                x: { grid: { display: false }, ticks: { color: '#94A3B8' } }
              },
              plugins: { legend: { display: false } } 
            }}
          />
        </ChartCard>
      </div>
      
      <div className="grid grid-cols-1">
        <ChartCard title="Monthly Liability Trend" icon={<TrendingUp size={18} />}>
          <Line 
            data={{
              labels: data.monthly_trend.map((t: any) => t.month),
              datasets: [
                {
                  label: 'Liability (\u20B9)',
                  data: data.monthly_trend.map((t: any) => t.total_amt),
                  borderColor: '#0068B1',
                  backgroundColor: 'rgba(0, 104, 177, 0.05)',
                  fill: true,
                  tension: 0.4,
                  pointRadius: 6,
                  pointBackgroundColor: '#fff',
                  pointBorderWidth: 3
                }
              ]
            }}
            options={{
              scales: {
                y: { grid: { color: '#F1F5F9' }, ticks: { color: '#94A3B8' } },
                x: { grid: { display: false }, ticks: { color: '#94A3B8' } }
              },
              plugins: { legend: { display: false } }
            }}
          />
        </ChartCard>
      </div>
    </div>
  );
}
