"use client";

import { useState } from "react";
import { AlertCircle, Download, Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import StandardCard from "@/components/standard-card";

export default function ProductPage() {
  const [description, setDescription] = useState("");
  const [result, setResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const exampleChips = [
    "50 kg bags of 43 grade OPC cement",
    "TMT bars for construction",
    "Drinking water quality",
    "Steel reinforcement",
    "RCC concrete",
  ];

  const handleRecommend = async () => {
    if (!description.trim()) {
      setError("Please describe what you make");
      return;
    }

    setError("");
    setLoading(true);

    try {
      const params = new URLSearchParams({
        description: description.trim(),
      });

      const response = await fetch(`/api/v1/product/recommend?${params}`, {
        method: "GET",
        headers: { "Content-Type": "application/json" },
      });

      if (!response.ok) {
        throw new Error(`API error: ${response.status}`);
      }

      const data = await response.json();
      setResult(data);
    } catch (err: any) {
      setError(err.message || "Failed to get recommendations");
    } finally {
      setLoading(false);
    }
  };

  const downloadChecklist = () => {
    if (!result?.checklist) return;

    const csv = [
      ["Designation", "Title", "Role", "Mandatory", "Current", "Evidence"].join(
        ","
      ),
      ...result.checklist.map((row: any) =>
        [
          row.designation,
          `"${row.title.replace(/"/g, '""')}"`,
          row.role,
          row.mandatory,
          row.current,
          row.why,
        ].join(",")
      ),
    ].join("\n");

    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `standards-${new Date().toISOString().split("T")[0]}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-orange-50 to-white">
      <div className="container mx-auto px-4 py-12">
        <div className="max-w-4xl mx-auto">
          {/* Header */}
          <div className="text-center mb-12">
            <h1 className="text-4xl font-bold text-gray-900 mb-2">
              Find Your Standards
            </h1>
            <p className="text-lg text-gray-600">
              Discover applicable Indian Standards for your product
            </p>
          </div>

          {/* Input Section */}
          <Card className="mb-8 border-orange-200 shadow-lg">
            <CardHeader className="bg-gradient-to-r from-orange-50 to-amber-50">
              <CardTitle className="text-orange-900">What Do You Make?</CardTitle>
            </CardHeader>
            <CardContent className="pt-6">
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="E.g., 50 kg bags of 43 grade ordinary portland cement for construction"
                className="w-full p-4 border-2 border-gray-300 rounded-lg focus:outline-none focus:border-orange-500 min-h-24 resize-none"
                onKeyDown={(e) => {
                  if (e.key === "Enter" && e.ctrlKey) {
                    handleRecommend();
                  }
                }}
              />

              {/* Example Chips */}
              <div className="mt-4 flex flex-wrap gap-2">
                {exampleChips.map((chip) => (
                  <button
                    key={chip}
                    onClick={() => setDescription(chip)}
                    className="px-3 py-1 bg-orange-100 hover:bg-orange-200 text-orange-900 rounded-full text-sm transition-colors"
                  >
                    {chip}
                  </button>
                ))}
              </div>

              {/* Action Buttons */}
              <div className="mt-6 flex gap-3">
                <Button
                  onClick={handleRecommend}
                  disabled={loading || !description.trim()}
                  className="bg-orange-600 hover:bg-orange-700 text-white px-6"
                >
                  {loading ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Searching...
                    </>
                  ) : (
                    "Get Recommendations"
                  )}
                </Button>
              </div>

              {/* Disclaimer */}
              <p className="mt-4 text-xs text-gray-500">
                ⚠️ This is a pointer to standards, not a certification verdict.
                Always verify with the official BIS.
              </p>
            </CardContent>
          </Card>

          {/* Error */}
          {error && (
            <Alert className="mb-8 border-red-200 bg-red-50">
              <AlertCircle className="h-4 w-4 text-red-600" />
              <AlertDescription className="text-red-800">{error}</AlertDescription>
            </Alert>
          )}

          {/* Results */}
          {result && (
            <div className="space-y-8">
              {/* Coverage */}
              {result.coverage?.warnings?.length > 0 && (
                <Alert className="border-yellow-200 bg-yellow-50">
                  <AlertCircle className="h-4 w-4 text-yellow-600" />
                  <AlertDescription className="text-yellow-800">
                    {result.coverage.warnings.join(" ")}
                  </AlertDescription>
                </Alert>
              )}

              {/* Primary Standards */}
              {result.primary?.length > 0 && (
                <Card className="border-green-200 shadow-md">
                  <CardHeader className="bg-gradient-to-r from-green-50 to-emerald-50">
                    <div className="flex justify-between items-center">
                      <CardTitle className="text-green-900">
                        Applicable Standards ({result.primary.length})
                      </CardTitle>
                      {result.checklist?.length > 0 && (
                        <Button
                          onClick={downloadChecklist}
                          variant="outline"
                          size="sm"
                          className="border-green-300 text-green-700 hover:bg-green-50"
                        >
                          <Download className="w-4 h-4 mr-2" />
                          CSV
                        </Button>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent className="pt-6">
                    <div className="space-y-3">
                      {result.primary.map((standard: any, idx: number) => (
                        <div
                          key={idx}
                          className="p-4 border border-green-100 rounded-lg hover:bg-green-50 transition-colors"
                        >
                          <div className="flex items-start justify-between mb-2">
                            <div>
                              <p className="font-mono font-bold text-green-900">
                                {standard.designation}
                              </p>
                              <p className="text-sm text-gray-700">
                                {standard.title}
                              </p>
                            </div>
                            <div className="flex gap-1 flex-wrap justify-end">
                              {standard.is_mandatory && (
                                <Badge className="bg-red-500 text-white">
                                  Mandatory
                                </Badge>
                              )}
                              <Badge variant="outline">
                                {standard.role.replace(/_/g, " ")}
                              </Badge>
                            </div>
                          </div>
                          <div className="text-xs text-gray-500 mt-2">
                            {standard.why.startsWith("alias:") && (
                              <span className="text-blue-600">
                                ✓ Direct product match
                              </span>
                            )}
                            {standard.why.startsWith("hybrid:") && (
                              <span className="text-purple-600">
                                ✓ Semantic match (confidence:{" "}
                                {Math.round(standard.score * 100)}%)
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Related Standards */}
              {result.related?.length > 0 && (
                <Card className="border-blue-200 shadow-md">
                  <CardHeader className="bg-gradient-to-r from-blue-50 to-cyan-50">
                    <CardTitle className="text-blue-900">
                      Related Standards ({result.related.length})
                    </CardTitle>
                    <p className="text-xs text-blue-700 mt-1">
                      Test methods, codes of practice, and supporting standards
                    </p>
                  </CardHeader>
                  <CardContent className="pt-6">
                    <div className="space-y-2">
                      {result.related.map((standard: any, idx: number) => (
                        <div
                          key={idx}
                          className="p-3 border border-blue-100 rounded text-sm hover:bg-blue-50 transition-colors"
                        >
                          <div className="flex justify-between items-start">
                            <div>
                              <p className="font-mono font-semibold text-blue-900">
                                {standard.designation}
                              </p>
                              <p className="text-gray-700">
                                {standard.title}
                              </p>
                            </div>
                            <Badge variant="outline" className="whitespace-nowrap">
                              {standard.role.replace(/_/g, " ")}
                            </Badge>
                          </div>
                        </div>
                      ))}
                    </div>
                  </CardContent>
                </Card>
              )}

              {/* Empty State */}
              {!result.primary?.length && !result.related?.length && (
                <Alert>
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription>
                    No standards found. Try describing your product with more
                    common terms.
                  </AlertDescription>
                </Alert>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
