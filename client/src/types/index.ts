export interface KPIStats {
  total_claims: number;
  total_incurred: number;
  avg_claim: number;
  cashless_pct: string;
  cashless_count: number;
  reimb_count: number;
  approval_rate: string;
  approved_count: number;
}

export interface FraudFlag {
  claim_id: string;
  hospital: string;
  amount: number;
  signals?: string[];
}

export interface ChartData {
  hospital?: string;
  month?: string;
  total_amt: number;
  [key: string]: any;
}

export interface AnalysisData {
  file: string;
  kpis: KPIStats;
  ai_narrative: string;
  fraud_flags: FraudFlag[];
  outliers?: FraudFlag[];
  hospital_breakdown: ChartData[];
  monthly_trend: ChartData[];
  details: Record<string, any>[];
}
