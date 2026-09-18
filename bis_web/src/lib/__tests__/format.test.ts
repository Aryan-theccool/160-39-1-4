import { describe, expect, it } from "vitest";

import {
  byDecade,
  countBy,
  formatMs,
  foundByLabel,
  gradeStyle,
  matchStrength,
  scorePercent,
  statusLabel,
  truncate,
} from "@/lib/format";
import type { SearchResult, StandardSummary } from "@/lib/api";

function result(overrides: Partial<SearchResult>): SearchResult {
  return {
    id: "x",
    designation: "IS 269:2015",
    title: "Portland cement",
    division: "Civil Engineering",
    year: 2015,
    is_current: true,
    score: 0.04,
    rerank_score: 2,
    found_by: {},
    archive_url: "",
    text: "",
    collection: "chunks",
    ...overrides,
  };
}

describe("matchStrength", () => {
  it("is 1 for the best hit and a fraction for the rest", () => {
    const results = [result({ score: 0.04 }), result({ score: 0.01 })];
    expect(matchStrength(results[0], results)).toBe(1);
    expect(matchStrength(results[1], results)).toBeCloseTo(0.25, 5);
  });

  it("stays within 0..1 even if a score exceeds the set maximum", () => {
    // Sorting is the API's job; if a caller passes an unsorted or partial list
    // the meter must not overflow its track.
    const results = [result({ score: 0.1 }), result({ score: 0.2 })];
    expect(matchStrength(results[1], results)).toBe(1);
    expect(matchStrength(results[0], results)).toBeCloseTo(0.5, 5);
  });

  it("never divides by zero when every score is zero", () => {
    const results = [result({ score: 0 }), result({ score: 0 })];
    expect(matchStrength(results[0], results)).toBe(0);
  });

  it("handles a single result and an empty set", () => {
    const only = result({ score: 0.033 });
    expect(matchStrength(only, [only])).toBe(1);
    expect(matchStrength(only, [])).toBe(0);
  });
});

describe("foundByLabel", () => {
  it("names only the retrievers that actually returned the hit", () => {
    expect(foundByLabel({ "bm25:chunks": 3 })).toBe("keyword");
    expect(foundByLabel({ "dense:chunks": 2 })).toBe("semantic");
    expect(foundByLabel({ "bm25:chunks": 1, "dense:chunks": 1 })).toBe("keyword + semantic");
  });

  it("falls back honestly when the API reports no source", () => {
    expect(foundByLabel({})).toBe("retrieved");
  });

  it("does not claim a source for a zero count", () => {
    expect(foundByLabel({ "bm25:chunks": 0 })).toBe("retrieved");
  });
});

describe("countBy", () => {
  const rows = [
    { division: "Civil", year: 2000 },
    { division: "Civil", year: 2010 },
    { division: "Electrical", year: 2000 },
    { division: "", year: 2000 },
    { division: "Civil", year: 0 },
  ];

  it("counts and sorts by frequency descending", () => {
    expect(countBy(rows, (row) => row.division)).toEqual([
      { label: "Civil", count: 3 },
      { label: "Electrical", count: 1 },
    ]);
  });

  it("skips empty values rather than charting a blank category", () => {
    const labels = countBy(rows, (row) => row.division).map((row) => row.label);
    expect(labels).not.toContain("");
  });

  it("ties break alphabetically so the chart order is stable between renders", () => {
    const tied = [{ key: "b" }, { key: "a" }];
    expect(countBy(tied, (row) => row.key).map((row) => row.label)).toEqual(["a", "b"]);
  });
});

describe("byDecade", () => {
  function standard(year: number): StandardSummary {
    return {
      designation: `IS ${year}`,
      canonical: `x${year}`,
      title: "t",
      division: "Civil",
      committee: "CED 2",
      year,
      is_current: true,
      superseded_by: "",
      is_compulsory: false,
      archive_url: "",
    };
  }

  it("buckets years into decades, oldest first", () => {
    const rows = [standard(2001), standard(2009), standard(1985), standard(1994)];
    expect(byDecade(rows)).toEqual([
      { label: "1980s", count: 1, decade: 1980 },
      { label: "1990s", count: 1, decade: 1990 },
      { label: "2000s", count: 2, decade: 2000 },
    ]);
  });

  it("omits a decade with no standards instead of charting a zero", () => {
    const decades = byDecade([standard(1970), standard(2010)]).map((row) => row.label);
    expect(decades).toEqual(["1970s", "2010s"]);
  });

  it("ignores missing and implausible years", () => {
    expect(byDecade([standard(0), standard(-5), standard(1899)])).toEqual([]);
  });
});

describe("gradeStyle", () => {
  it("maps every grade the API can return", () => {
    for (const grade of [
      "FULLY COMPLIANT",
      "MOSTLY COMPLIANT",
      "PARTIALLY COMPLIANT",
      "NON-COMPLIANT",
    ]) {
      expect(gradeStyle(grade).ring).toMatch(/^#/);
    }
  });

  it("falls back to a neutral colour for an unknown grade", () => {
    // The API may add a grade; the UI must render it rather than crash.
    expect(gradeStyle("SOMETHING NEW").ring).toBe("#94a3b8");
  });
});

describe("small formatters", () => {
  it("clamps the score percentage", () => {
    expect(scorePercent(0.7667)).toBe(77);
    expect(scorePercent(1.5)).toBe(100);
    expect(scorePercent(-1)).toBe(0);
  });

  it("formats milliseconds at the right precision", () => {
    expect(formatMs(0.4)).toBe("<1 ms");
    expect(formatMs(9.44)).toBe("9.4 ms");   // sub-10 keeps the decimal
    expect(formatMs(12.24)).toBe("12 ms");   // above 10 it is noise
    expect(formatMs(240)).toBe("240 ms");
    expect(formatMs(2400)).toBe("2.40 s");
  });

  it("truncates with an ellipsis and leaves short text alone", () => {
    expect(truncate("hello", 10)).toBe("hello");
    expect(truncate("hello world", 5)).toBe("hello…");
  });

  it("describes supersession with the replacement when it is known", () => {
    expect(statusLabel({ is_current: true, superseded_by: "" })).toBe("Current");
    expect(statusLabel({ is_current: false, superseded_by: "IS 456:2000" })).toBe(
      "Superseded by IS 456:2000",
    );
    expect(statusLabel({ is_current: false, superseded_by: "" })).toBe("Superseded");
  });
});
