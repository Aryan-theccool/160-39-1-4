/**
 * The typed client for the BIS Standards API.
 *
 * Everything here mirrors `bis_scraper/src/bis_api/models/response.py`. Where a
 * field is optional in the API it is optional here too, because the API is
 * genuinely allowed to omit it -- `compliance` is null on a question that is not
 * about compliance, `source_document` is null on the JSON endpoints. Typing
 * those as required would push non-null assertions into the pages and turn a
 * real, meaningful "not applicable" into a runtime crash.
 */
import axios, { AxiosError, type AxiosRequestConfig } from "axios";

/**
 * Relative by default, proxied by next.config.mjs.
 *
 * `http://localhost:8000/api/v1` is the obvious value and the wrong default:
 * when the browser is not on the same host as the API -- a container, a tunnel,
 * a preview URL -- `localhost` means the *user's* machine and every request
 * fails with a connection error that reads like the API is down. Set
 * NEXT_PUBLIC_API_URL to bypass the proxy when the API really is elsewhere.
 */
export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "/api/v1";

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60_000, // generous: an LLM-backed answer can legitimately take a while
  headers: { "Content-Type": "application/json" },
});

/** The one error shape the API produces, for every status code. */
export interface ApiErrorBody {
  error: string;
  detail: string;
  request_id: string;
  status_code: number;
}

/**
 * A failed request, with the API's own explanation kept intact.
 *
 * The API already writes a better error message than this client ever could --
 * it knows the corpus size, the limit, the variable that changes the limit --
 * so the job here is to carry `detail` through untouched and never replace it
 * with a generic "Request failed".
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId?: string;

  constructor(status: number, code: string, detail: string, requestId?: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
  }
}

function toApiError(error: unknown): ApiError {
  if (error instanceof AxiosError) {
    const body = error.response?.data as Partial<ApiErrorBody> | undefined;
    if (body?.detail) {
      return new ApiError(
        body.status_code ?? error.response?.status ?? 0,
        body.error ?? "error",
        body.detail,
        body.request_id,
      );
    }
    if (error.code === "ECONNABORTED") {
      return new ApiError(0, "timeout", "The API took too long to answer. It may still be starting up.");
    }
    if (!error.response) {
      return new ApiError(
        0,
        "network_error",
        `Could not reach the API at ${API_BASE_URL}. Start it with: uvicorn bis_api.main:app --port 8000`,
      );
    }
    return new ApiError(
      error.response.status,
      "error",
      error.response.statusText || `HTTP ${error.response.status}`,
    );
  }
  return new ApiError(0, "unknown_error", String(error));
}

async function request<T>(config: AxiosRequestConfig): Promise<T> {
  try {
    const response = await api.request<T>(config);
    return response.data;
  } catch (error) {
    throw toApiError(error);
  }
}

// ---------------------------------------------------------------------------
// health
// ---------------------------------------------------------------------------
export type ServiceStatus = "ok" | "degraded" | "unavailable";

export interface Health {
  status: ServiceStatus;
  version: string;
  detail: string;
  corpus: {
    standards: number;
    /** Canonical count: direct read of knowledge_base.json, bypasses the 3-way merger. */
    knowledge_base_standards?: number;
    chunks: number;
    current: number;
    superseded: number;
    compulsory: number;
    divisions: number;
    year_range: number[];
    data_dir: string;
  };
  retrieval: {
    bm25_chunks: number;
    bm25_standards: number;
    dense_enabled: boolean;
    vectors: number;
    embedder: string;
    backends_available: string[];
    reranker: string;
    error?: string;
  };
  qco: {
    entries: number;
    source: string;
    verified: boolean;
    /** Gazette-verified QCO mappings (evidence_state === "VERIFIED") */
    verified_count?: number;
    superseded_count?: number;
    not_applicable_count?: number;
    not_found_count?: number;
    ambiguous_count?: number;
    seed_unverified_count?: number;
    coverage_note?: string;
  };
  llm: { provider: string; is_llm: boolean };
  startup_ms: number;
  uptime_s: number;
  issues: string[];
}

export const health = () => request<Health>({ url: "/health", method: "GET" });

// ---------------------------------------------------------------------------
// search
// ---------------------------------------------------------------------------
export interface SearchResult {
  id: string;
  designation: string;
  title: string;
  division: string;
  year: number;
  is_current: boolean;
  /**
   * Reciprocal-rank-fusion score. Meaningful only *within* a result set and
   * only for ordering -- it is not a probability. See `matchStrength` in
   * format.ts for how this is presented without overclaiming.
   */
  score: number;
  rerank_score: number;
  found_by: Record<string, number>;
  archive_url: string;
  text: string;
  collection: string;
}

export interface SearchResponse {
  query: string;
  intent: string;
  filter: Record<string, unknown>;
  reranker: string;
  notes: string[];
  supersession_warnings: string[];
  results: SearchResult[];
  took_ms: number;
}

export interface SearchParams {
  q: string;
  limit?: number;
  domain?: string;
  is_number?: string;
  year?: number;
  include_superseded?: boolean;
  include_passages?: boolean;
  reranker?: string;
}

export const search = (params: SearchParams) =>
  request<SearchResponse>({ url: "/search", method: "GET", params });

// ---------------------------------------------------------------------------
// recommend
// ---------------------------------------------------------------------------
export interface Citation {
  designation: string;
  title: string;
  canonical: string;
  is_current: boolean;
  superseded_by: string;
  archive_url: string;
  chunk_id: string;
}

export interface ComplianceStandardRow {
  input: string;
  designation: string;
  canonical: string;
  title: string;
  found_in_dataset: boolean;
  is_current: boolean;
  is_mandatory: boolean;
  applicability?: "APPLICABLE" | "NOT_APPLICABLE" | "CANDIDATE" | string;
  applicability_reason?: string;
  qco_evidence_state?: "VERIFIED" | "SUPERSEDED_OR_CHANGED" | "NOT_APPLICABLE" | "NOT_FOUND" | "AMBIGUOUS" | "SEED_UNVERIFIED" | string;
  qco_source?: string;
  qco_source_url?: string;
  qco_title?: string;
  qco_notification?: string;
  qco_ministry?: string;
  qco_effective_date?: string;
  qco_evidence_notes?: string;
}

export interface SpecificationCheck {
  parameter: string;
  product_value: string;
  required_value: string;
  operator: string;
  unit: string;
  status: "PASS" | "FAIL" | "UNKNOWN" | "NOT_APPLICABLE" | string;
  standard?: string;
  clause?: string;
  evidence?: string;
  explanation?: string;
  source_url?: string;
  chunk_id?: string;
}

export interface ProductSpec {
  parameter: string;
  raw_value: string;
  numeric_value?: number;
  unit?: string;
  base_value?: number;
  base_unit?: string;
}

export interface ComplianceResult {
  product_description: string;
  sector: string;
  compliance_status: "COMPLIANT" | "PARTIAL" | "NON_COMPLIANT" | "UNKNOWN" | string;
  grade:
    | "FULLY COMPLIANT"
    | "MOSTLY COMPLIANT"
    | "PARTIALLY COMPLIANT"
    | "NON-COMPLIANT"
    | string;
  compliance_score: number;
  qco_source: string;
  qco_verified: boolean;
  qco_size: number;
  mandatory_expected: string[];
  mandatory_present: string[];
  mandatory_missing: string[];
  mandatory_candidates: string[];
  sector_candidates: string[];
  superseded_used: { used: string; replace_with: string; replacement_in_dataset: boolean }[];
  conflicts: { type?: string; standards?: string; detail?: string }[];
  product_specifications?: Record<string, ProductSpec>;
  specification_checks?: SpecificationCheck[];
  action_items: string[];
  limitations: string[];
  notes: string[];
  standards: ComplianceStandardRow[];
  weights: Record<string, number>;
  weights_redistributed: boolean;
  grade_capped_by: string;
  took_ms: number;
}

export interface SourceDocument {
  extractor: string;
  pages: number;
  chars: number;
  ok: boolean;
  reason: string;
  warnings: string[];
  filename?: string;
}

export interface ProductUnderstanding {
  product: string;
  application?: string;
  specifications?: Record<string, string>;
}

export interface ApplicableStandard {
  designation: string;
  title: string;
  relevance: string;
  reason: string;
  status: "current" | "superseded" | "unknown" | string;
}

export interface RelatedStandard {
  designation: string;
  title: string;
  relationship: string;
}

export interface EvidenceItem {
  designation: string;
  chunk_id?: string;
  reason: string;
}

export interface StructuredReport {
  summary: string;
  product_understanding?: ProductUnderstanding;
  applicable_standards?: ApplicableStandard[];
  related_standards?: RelatedStandard[];
  compliance_notes?: string[];
  warnings?: string[];
  evidence?: EvidenceItem[];
}

export interface RecommendResponse {
  question: string;
  answer: string;
  mode: "extractive" | "llm" | string;
  generator: string;
  intent: string;
  grounded: boolean;
  citations: Citation[];
  unsupported_citations: string[];
  warnings: string[];
  notes: string[];
  compliance: ComplianceResult | null;
  report?: StructuredReport | null;
  passages: unknown;
  source_document: SourceDocument | null;
  detected_designations: string[] | null;
  took_ms: number;
}

export interface RecommendParams {
  query: string;
  top_k?: number;
  include_passages?: boolean;
  run_compliance?: boolean;
}

export const recommend = (params: RecommendParams) =>
  request<RecommendResponse>({ url: "/recommend", method: "POST", data: params });

export interface PdfRecommendResponse extends RecommendResponse {
  source_document: SourceDocument;
}

export async function recommendPdf(
  file: File,
  opts: { top_k?: number; include_passages?: boolean } = {},
): Promise<PdfRecommendResponse> {
  const form = new FormData();
  form.append("file", file, file.name);
  try {
    const response = await api.post<PdfRecommendResponse>("/recommend/pdf", form, {
      params: opts,
      headers: { "Content-Type": "multipart/form-data" },
      // Extraction plus retrieval is slower than a text query, and an
      // upload has no useful "cancel" affordance in a drop zone.
      timeout: 120_000,
    });
    return response.data;
  } catch (error) {
    throw toApiError(error);
  }
}

// ---------------------------------------------------------------------------
// report export (DOCX and PDF)
// ---------------------------------------------------------------------------
export async function downloadReportDocx(data: Partial<RecommendResponse>): Promise<string> {
  try {
    const response = await api.post("/report/docx", data, {
      responseType: "blob",
      timeout: 30_000,
    });
    const disposition = response.headers["content-disposition"] || "";
    let filename = "bis_standards_report.docx";
    const match = disposition.match(/filename="?([^"]+)"?/);
    if (match && match[1]) {
      filename = match[1];
    }
    const blob = new Blob([response.data], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
    return filename;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function downloadReportPdf(data: Partial<RecommendResponse>): Promise<string> {
  try {
    const response = await api.post("/report/pdf", data, {
      responseType: "blob",
      timeout: 30_000,
    });
    const disposition = response.headers["content-disposition"] || "";
    let filename = "bis_standards_report.pdf";
    const match = disposition.match(/filename="?([^"]+)"?/);
    if (match && match[1]) {
      filename = match[1];
    }
    const blob = new Blob([response.data], {
      type: "application/pdf",
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
    return filename;
  } catch (error) {
    throw toApiError(error);
  }
}

// ---------------------------------------------------------------------------
// compliance
// ---------------------------------------------------------------------------
export interface ComplianceParams {
  product_description: string;
  standards?: string[];
  sector?: string;
  top_k?: number;
}

export const complianceCheck = (params: ComplianceParams) =>
  request<ComplianceResult>({ url: "/compliance/check", method: "POST", data: params });

/** The printable gap report. Returned as HTML by the API, opened in a new tab. */
export function gapReportUrl(product: string, standards: string[]): string {
  const params = new URLSearchParams({ product });
  standards.forEach((s) => params.append("standard", s));
  // Relative, so it resolves against whatever origin the app is served from.
  return `${API_BASE_URL}/compliance/report?${params.toString()}`;
}

/**
 * Download the gap report as a file. Fetches the HTML report with
 * `?download=1` so the server sends `Content-Disposition: attachment`, then
 * saves it locally. The user can open the saved `.html` file in any browser
 * and print to PDF from there.
 */
export async function downloadGapReportPdf(
  product: string,
  standards: string[],
): Promise<void> {
  const params = new URLSearchParams({ product, download: "1" });
  standards.forEach((s) => params.append("standard", s));
  const url = `${API_BASE_URL}/compliance/report?${params.toString()}`;

  const response = await api.get<Blob>(url, {
    responseType: "blob",
    timeout: 30_000,
  });

  const blob = new Blob([response.data], { type: "text/html" });
  const objectUrl = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.setAttribute("download", "bis_gap_report.html");
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(objectUrl);
}


// ---------------------------------------------------------------------------
// standards
// ---------------------------------------------------------------------------
export interface StandardSummary {
  designation: string;
  canonical: string;
  title: string;
  division: string;
  committee: string;
  year: number;
  is_current: boolean;
  superseded_by: string;
  is_compulsory: boolean;
  archive_url: string;
}

export interface StandardsPage {
  total: number;
  offset: number;
  limit: number;
  returned: number;
  facets: { divisions: string[]; committees: string[] };
  standards: StandardSummary[];
}

export interface StandardDetail extends StandardSummary {
  status: string;
  keywords: string[];
  supersession: {
    canonical: string;
    designation: string;
    replacement_designation: string;
    replacement_canonical: string;
    replacement_year: number;
    in_dataset: boolean;
  } | null;
  related: { designation: string; title: string; year: number; is_current: boolean }[];
}

/**
 * The API caps `limit` at 500. 197 standards fit in one page, so the browser
 * and the dashboard fetch the whole list once and filter in the client --
 * instant typing, no request per keystroke, and no endpoint to add.
 */
export const STANDARDS_PAGE_LIMIT = 500;

export interface StandardsParams {
  q?: string;
  division?: string;
  committee?: string;
  year?: number;
  current_only?: boolean;
  compulsory_only?: boolean;
  limit?: number;
  offset?: number;
}

export const listStandards = (params: StandardsParams = {}) =>
  request<StandardsPage>({ url: "/standards", method: "GET", params });

export const getStandard = (isNumber: string) =>
  request<StandardDetail>({
    url: `/standards/${encodeURIComponent(isNumber)}`,
    method: "GET",
  });

// ---------------------------------------------------------------------------
// feedback
// ---------------------------------------------------------------------------
export interface FeedbackParams {
  query: string;
  helpful: boolean;
  correct_is?: string | null;
  comment?: string | null;
  request_id?: string | null;
}

export const sendFeedback = (params: FeedbackParams) =>
  request<{ saved: boolean; path: string; message: string }>({
    url: "/feedback",
    method: "POST",
    data: params,
  });

// ---------------------------------------------------------------------------
// tender analysis & report export
// ---------------------------------------------------------------------------
export interface TenderClause {
  clause_id: string;
  heading: string;
  text: string;
  page_number: number;
  is_mandatory: boolean;
  standards_referenced: string[];
}

export interface TenderRequirement {
  req_id: string;
  clause_id: string;
  parameter: string;
  specified_value: string;
  unit: string;
  operator: string;
  is_mandatory: boolean;
  standard_reference?: string | null;
}

export interface TenderStandardAssessment {
  standard_code: string;
  status: "APPLICABLE" | "NOT_APPLICABLE" | "CANDIDATE" | string;
  relevance_score: number;
  reason: string;
  scope_summary: string;
  qco_mandatory: boolean;
  qco_evidence_state?: "VERIFIED" | "SUPERSEDED_OR_CHANGED" | "NOT_APPLICABLE" | "NOT_FOUND" | "AMBIGUOUS" | "SEED_UNVERIFIED" | string;
  qco_display?: string;
}

export interface TenderRequirementEvaluation {
  req_id: string;
  parameter: string;
  specified_value: string;
  standard_code: string;
  standard_requirement: string;
  status: "PASS" | "FAIL" | "UNKNOWN" | string;
  reason: string;
  clause_reference: string;
  confidence: number;
}

export interface TenderComplianceMatrix {
  tender_title: string;
  product_type: string;
  total_clauses: number;
  total_requirements: number;
  standards_assessed: TenderStandardAssessment[];
  requirement_evaluations: TenderRequirementEvaluation[];
  summary: string;
  overall_status: "COMPLIANT" | "PARTIAL" | "NON_COMPLIANT" | "UNKNOWN" | string;
  compliance_score: number;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | string;
  key_risks: string[];
  recommendations: string[];
  created_at: string;
  qco_source?: string;
  qco_verified?: boolean;
}

export interface TenderAnalysisResponse {
  filename?: string | null;
  document_type: string;
  pages: number;
  total_characters: number;
  clauses: TenderClause[];
  requirements: TenderRequirement[];
  compliance_matrix?: TenderComplianceMatrix | null;
  standards_detected: string[];
  processing_time_ms: number;
  error?: string | null;
}

export interface TenderAnalyzeTextParams {
  tender_text: string;
  title?: string;
  product_type?: string;
  top_k?: number;
}

export async function analyzeTenderFile(
  file: File,
  opts: { product_type?: string; top_k?: number } = {},
): Promise<TenderAnalysisResponse> {
  const form = new FormData();
  form.append("file", file, file.name);
  try {
    const response = await api.post<TenderAnalysisResponse>("/tender/analyze/file", form, {
      params: opts,
      headers: { "Content-Type": "multipart/form-data" },
      timeout: 120_000,
    });
    return response.data;
  } catch (error) {
    throw toApiError(error);
  }
}

export function analyzeTenderText(
  params: TenderAnalyzeTextParams,
): Promise<TenderAnalysisResponse> {
  return request<TenderAnalysisResponse>({
    url: "/tender/analyze/text",
    method: "POST",
    data: params,
  });
}

export async function downloadTenderReportDocx(
  data: TenderComplianceMatrix | TenderAnalysisResponse | Record<string, unknown>,
): Promise<string> {
  try {
    const response = await api.post("/tender/report/docx", data, {
      responseType: "blob",
      timeout: 30_000,
    });
    const disposition = response.headers["content-disposition"] || "";
    let filename = "tender_compliance_report.docx";
    const match = disposition.match(/filename="?([^"]+)"?/);
    if (match && match[1]) {
      filename = match[1];
    }
    const blob = new Blob([response.data], {
      type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
    return filename;
  } catch (error) {
    throw toApiError(error);
  }
}

export async function downloadTenderReportPdf(
  data: TenderComplianceMatrix | TenderAnalysisResponse | Record<string, unknown>,
): Promise<string> {
  try {
    const response = await api.post("/tender/report/pdf", data, {
      responseType: "blob",
      timeout: 30_000,
    });
    const disposition = response.headers["content-disposition"] || "";
    let filename = "tender_compliance_report.pdf";
    const match = disposition.match(/filename="?([^"]+)"?/);
    if (match && match[1]) {
      filename = match[1];
    }
    const blob = new Blob([response.data], {
      type: "application/pdf",
    });
    const url = window.URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.setAttribute("download", filename);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    window.URL.revokeObjectURL(url);
    return filename;
  } catch (error) {
    throw toApiError(error);
  }
}


