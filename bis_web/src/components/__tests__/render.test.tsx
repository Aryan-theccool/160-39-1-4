import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { AnswerPanel } from "@/components/answer-panel";
import { MatchMeter } from "@/components/match-meter";
import { ScoreGauge } from "@/components/score-gauge";
import { StandardCard } from "@/components/standard-card";
import type { RecommendResponse, SearchResult } from "@/lib/api";

/**
 * Render checks for the pieces the brief calls out by name -- the score gauge
 * and the result cards -- plus the two places where this UI makes a claim about
 * how much to trust the output. Those claims are easy to break silently.
 */
function result(overrides: Partial<SearchResult> = {}): SearchResult {
  return {
    id: "IS|269|None|None|2015__chunk_2",
    designation: "IS 269:2015",
    title: "Ordinary Portland cement, 33 grade",
    division: "Civil Engineering",
    year: 2015,
    is_current: true,
    score: 0.04,
    rerank_score: 2.5,
    found_by: { "bm25:chunks": 1, "dense:chunks": 2 },
    archive_url: "https://archive.org/details/gov.in.is.269",
    text: "This standard covers the manufacture of ordinary Portland cement.",
    collection: "chunks",
    ...overrides,
  };
}

describe("ScoreGauge", () => {
  it("shows the score as a whole number out of 100", () => {
    const html = renderToStaticMarkup(
      <ScoreGauge score={0.7667} label="MOSTLY COMPLIANT" color="#f59e0b" />,
    );
    expect(html).toContain(">77<");
    expect(html).toContain("out of 100");
    expect(html).toContain("MOSTLY COMPLIANT");
  });

  it("carries the score in an accessible label, not only in the arc", () => {
    // The number is drawn as SVG text and the arc is decorative; without this
    // a screen reader gets nothing but the grade name.
    const html = renderToStaticMarkup(<ScoreGauge score={0.8} />);
    expect(html).toContain('aria-label="Compliance score 80 out of 100"');
    expect(html).toContain('role="img"');
  });

  it("clamps out-of-range input instead of drawing past the dial", () => {
    expect(renderToStaticMarkup(<ScoreGauge score={1.4} />)).toContain(">100<");
    expect(renderToStaticMarkup(<ScoreGauge score={-0.2} />)).toContain(">0<");
  });
});

describe("MatchMeter", () => {
  it("labels the value as a share of the best hit, never as confidence", () => {
    const html = renderToStaticMarkup(<MatchMeter value={0.5} />);
    expect(html).toContain("50% of best");
    // The one word this component must never print.
    expect(html.toLowerCase()).not.toContain("confidence");
    expect(html.toLowerCase()).not.toContain("confident");
  });

  it("keeps a visible bar at zero so the row does not look broken", () => {
    const html = renderToStaticMarkup(<MatchMeter value={0} />);
    expect(html).toContain("width:4%");
    expect(html).toContain("0% of best");
  });
});

describe("StandardCard", () => {
  it("renders the designation, title, division and year", () => {
    const html = renderToStaticMarkup(<StandardCard result={result()} results={[result()]} rank={1} />);
    expect(html).toContain("IS 269:2015");
    expect(html).toContain("Ordinary Portland cement, 33 grade");
    expect(html).toContain("Civil Engineering");
    expect(html).toContain("2015");
  });

  it("marks a superseded edition instead of presenting it as current", () => {
    const superseded = result({ is_current: false, designation: "IS 269:1989" });
    const html = renderToStaticMarkup(
      <StandardCard result={superseded} results={[superseded]} rank={1} />,
    );
    expect(html).toContain("Superseded");
    expect(html).not.toContain(">Current<");
  });

  it("names the retrievers that found the hit", () => {
    const html = renderToStaticMarkup(<StandardCard result={result()} results={[result()]} rank={2} />);
    expect(html).toContain("found by keyword + semantic");
  });

  it("opens the source document in a new tab safely", () => {
    const html = renderToStaticMarkup(<StandardCard result={result()} results={[result()]} rank={1} />);
    expect(html).toContain('rel="noreferrer noopener"');
    expect(html).toContain("archive.org/details/gov.in.is.269");
  });

  it("shows the rank it was given", () => {
    const html = renderToStaticMarkup(<StandardCard result={result()} results={[result()]} rank={3} />);
    expect(html).toContain(">3<");
  });
});

describe("AnswerPanel", () => {
  function answer(overrides: Partial<RecommendResponse> = {}): RecommendResponse {
    return {
      question: "what is IS 1239?",
      answer: "IS 1239:2004 covers steel tubes.",
      mode: "extractive",
      generator: "extractive",
      intent: "lookup",
      grounded: true,
      citations: [
        {
          designation: "IS 1239:2004",
          title: "Steel tubes",
          canonical: "IS|1239|None|None|2004",
          is_current: true,
          superseded_by: "",
          archive_url: "https://archive.org/details/gov.in.is.1239",
          chunk_id: "",
        },
      ],
      unsupported_citations: [],
      warnings: [],
      notes: [],
      compliance: null,
      passages: null,
      source_document: null,
      detected_designations: null,
      took_ms: 11.7,
      ...overrides,
    };
  }

  it("distinguishes an extracted answer from a generated one", () => {
    expect(renderToStaticMarkup(<AnswerPanel answer={answer()} />)).toContain(
      "Extracted from the standards",
    );
    expect(
      renderToStaticMarkup(<AnswerPanel answer={answer({ mode: "llm" })} />),
    ).toContain("Generated by LLM");
  });

  it("says so when a citation could not be verified", () => {
    const html = renderToStaticMarkup(
      <AnswerPanel answer={answer({ grounded: false, unsupported_citations: ["IS 99999"] })} />,
    );
    expect(html).toContain("IS 99999");
    expect(html).toContain("not");
    expect(html).toContain("Unverified standard reference");
  });

  it("surfaces supersession on a citation and names the replacement", () => {
    const html = renderToStaticMarkup(
      <AnswerPanel
        answer={answer({
          citations: [
            {
              designation: "IS 456:1978",
              title: "Plain and reinforced concrete",
              canonical: "IS|456|None|None|1978",
              is_current: false,
              superseded_by: "IS 456:2000",
              archive_url: "",
              chunk_id: "",
            },
          ],
        })}
      />,
    );
    expect(html).toContain("Superseded");
    expect(html).toContain("Replaced by IS 456:2000");
  });

  it("prints every warning the API returned", () => {
    const html = renderToStaticMarkup(
      <AnswerPanel answer={answer({ warnings: ["IS 269:1989 is superseded by IS 269:2015"] })} />,
    );
    expect(html).toContain("IS 269:1989 is superseded by IS 269:2015");
  });
});

describe("TenderMatrixView", () => {
  it("renders the tender title, compliance score, and evaluation matrix", async () => {
    const { TenderMatrixView } = await import("@/components/tender-matrix-view");
    const html = renderToStaticMarkup(
      <TenderMatrixView
        analysis={{
          filename: "tender_spec.pdf",
          document_type: "pdf",
          pages: 2,
          total_characters: 1500,
          clauses: [
            {
              clause_id: "CLAUSE-01",
              heading: "Operating Voltage",
              text: "The luminaires shall operate at 230 V AC.",
              page_number: 1,
              is_mandatory: true,
              standards_referenced: ["IS 10322"],
            },
          ],
          requirements: [
            {
              req_id: "REQ-01",
              clause_id: "CLAUSE-01",
              parameter: "Supply Voltage",
              specified_value: "230 V",
              unit: "V",
              operator: "==",
              is_mandatory: true,
              standard_reference: "IS 10322",
            },
          ],
          compliance_matrix: {
            tender_title: "Smart Street Light Tender",
            product_type: "LED Luminaire",
            total_clauses: 1,
            total_requirements: 1,
            standards_assessed: [
              {
                standard_code: "IS 10322 (Part 5/Sec 3):2012",
                status: "APPLICABLE",
                relevance_score: 0.95,
                reason: "Standard covers luminaires for road lighting.",
                scope_summary: "Luminaires for road and street lighting",
                qco_mandatory: true,
              },
            ],
            requirement_evaluations: [
              {
                req_id: "REQ-01",
                parameter: "Supply Voltage",
                specified_value: "230 V",
                standard_code: "IS 10322 (Part 5/Sec 3):2012",
                standard_requirement: "Rated voltage 240 V +/- 6%",
                status: "PASS",
                reason: "230 V falls within the 240 V +/- 6% supply range.",
                clause_reference: "Clause 3.2",
                confidence: 0.95,
              },
            ],
            summary: "Tender specifications comply with IS 10322.",
            overall_status: "COMPLIANT",
            compliance_score: 1.0,
            risk_level: "LOW",
            key_risks: [],
            recommendations: ["Ensure QCO certification is provided."],
            created_at: "2026-09-21T00:00:00Z",
          },
          standards_detected: ["IS 10322"],
          processing_time_ms: 120,
        }}
      />,
    );

    expect(html).toContain("Smart Street Light Tender");
    expect(html).toContain("100%");
    expect(html).toContain("Supply Voltage");
    expect(html).toContain("230 V");
    expect(html).toContain("PASS");
    expect(html).toContain("Word (.docx)");
    expect(html).toContain("PDF Report");
  });
});

