"use client";

import { useState } from "react";
import { AlertCircle, Download, Loader2, Sparkles, CheckCircle2, Filter, TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

interface Standard {
  designation: string;
  title: string;
  role: string;
  is_mandatory?: boolean;
  why: string;
  score?: number;
}

interface RecommendationResult {
  primary: Standard[];
  related: Standard[];
  checklist: Array<{
    designation: string;
    title: string;
    role: string;
    mandatory: boolean;
    current: boolean;
    why: string;
  }>;
  coverage?: {
    warnings: string[];
  };
}

export default function ProductPage() {
  const [description, setDescription] = useState("");
  const [result, setResult] = useState<RecommendationResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showRelated, setShowRelated] = useState(false);

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
    setShowRelated(false);

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

      const data: RecommendationResult = await response.json();
      setResult(data);
    } catch (err) {
      const errorMessage = err instanceof Error ? err.message : "Failed to get recommendations";
      setError(errorMessage);
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
      ...result.checklist.map((row) =>
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
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-blue-900 to-slate-900">
      {/* Background Elements */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none">
        <div className="absolute top-20 right-20 w-96 h-96 bg-blue-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob"></div>
        <div className="absolute bottom-20 left-20 w-96 h-96 bg-indigo-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-blob animation-delay-2000"></div>
      </div>

      <div className="relative z-10">
        <div className="container mx-auto px-4 py-16">
          <div className="max-w-5xl mx-auto">
            {/* Hero Header */}
            <div className="text-center mb-16 space-y-6">
              <div className="inline-block">
                <div className="flex items-center justify-center gap-2 px-4 py-2 rounded-full bg-blue-500/20 border border-blue-400/50 backdrop-blur-sm">
                  <Sparkles className="w-4 h-4 text-blue-300" />
                  <span className="text-sm font-medium text-blue-300">AI-Powered Standards Discovery</span>
                </div>
              </div>
              
              <div>
                <h1 className="text-5xl md:text-6xl font-bold bg-gradient-to-r from-blue-200 via-blue-100 to-indigo-200 bg-clip-text text-transparent mb-4">
                  Find Your Standards
                </h1>
                <p className="text-xl text-blue-100/80 max-w-2xl mx-auto">
                  Discover applicable Indian Standards for your product in seconds
                </p>
              </div>
            </div>

            {/* Search Card */}
            <Card className="mb-12 border-0 bg-white/95 backdrop-blur-xl shadow-2xl">
              <CardContent className="p-8">
                {/* Textarea */}
                <div className="mb-6">
                  <label className="block text-sm font-semibold text-gray-700 mb-3">
                    What do you manufacture?
                  </label>
                  <textarea
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Describe your product in detail... e.g., 50 kg bags of 43 grade OPC cement for construction"
                    className="w-full p-4 border-2 border-gray-200 rounded-xl focus:outline-none focus:border-blue-500 focus:ring-2 focus:ring-blue-100 min-h-28 resize-none transition-all text-gray-800 placeholder-gray-400"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && e.ctrlKey) {
                        handleRecommend();
                      }
                    }}
                  />
                </div>

                {/* Example Chips */}
                <div className="mb-8">
                  <p className="text-xs font-semibold text-gray-600 mb-3 uppercase tracking-wide">Popular examples</p>
                  <div className="flex flex-wrap gap-2">
                    {exampleChips.map((chip) => (
                      <button
                        key={chip}
                        onClick={() => setDescription(chip)}
                        className="px-3 py-2 bg-gradient-to-r from-blue-50 to-indigo-50 hover:from-blue-100 hover:to-indigo-100 text-gray-700 font-medium rounded-lg text-sm transition-all duration-200 border border-blue-200 hover:border-blue-400 hover:shadow-md"
                      >
                        {chip}
                      </button>
                    ))}
                  </div>
                </div>

                {/* Action Button */}
                <div className="flex gap-3">
                  <Button
                    onClick={handleRecommend}
                    disabled={loading || !description.trim()}
                    className="bg-gradient-to-r from-blue-600 to-blue-700 hover:from-blue-700 hover:to-blue-800 text-white px-8 py-3 rounded-lg font-semibold transition-all duration-200 shadow-lg hover:shadow-xl disabled:opacity-50"
                  >
                    {loading ? (
                      <>
                        <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                        Searching Standards...
                      </>
                    ) : (
                      <>
                        <TrendingUp className="w-4 h-4 mr-2" />
                        Get Recommendations
                      </>
                    )}
                  </Button>
                </div>

                {/* Disclaimer */}
                <p className="mt-6 text-xs text-gray-500 flex items-center gap-2">
                  <AlertCircle className="w-3 h-3" />
                  This is a pointer to standards, not a certification verdict. Always verify with official BIS.
                </p>
              </CardContent>
            </Card>

            {/* Error */}
            {error && (
              <Alert className="mb-8 border-0 bg-red-500/20 backdrop-blur-xl">
                <AlertCircle className="h-5 w-5 text-red-400" />
                <AlertDescription className="text-red-200 font-medium">{error}</AlertDescription>
              </Alert>
            )}

            {/* Results */}
            {result && (
              <div className="space-y-6 animate-fade-in">
                {/* Coverage Warning */}
                {result.coverage && result.coverage.warnings && result.coverage.warnings.length > 0 && (
                  <Alert className="border-0 bg-amber-500/20 backdrop-blur-xl border-l-4 border-amber-400">
                    <AlertCircle className="h-5 w-5 text-amber-300" />
                    <AlertDescription className="text-amber-100">
                      {result.coverage.warnings.join(" ")}
                    </AlertDescription>
                  </Alert>
                )}

                {/* Primary Standards */}
                {result.primary?.length > 0 && (
                  <Card className="border-0 bg-white/95 backdrop-blur-xl shadow-xl overflow-hidden">
                    <CardHeader className="bg-gradient-to-r from-green-50 to-emerald-50 pb-4">
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-3">
                          <div className="p-2 bg-green-200 rounded-lg">
                            <CheckCircle2 className="w-5 h-5 text-green-700" />
                          </div>
                          <div>
                            <CardTitle className="text-green-900">Applicable Standards</CardTitle>
                            <p className="text-xs text-green-700 mt-1">{result.primary.length} standards found</p>
                          </div>
                        </div>
                        {result.checklist?.length > 0 && (
                          <Button
                            onClick={downloadChecklist}
                            className="bg-green-600 hover:bg-green-700 text-white gap-2"
                          >
                            <Download className="w-4 h-4" />
                            Export CSV
                          </Button>
                        )}
                      </div>
                    </CardHeader>
                    <CardContent className="pt-6">
                      <div className="space-y-3">
                        {result.primary.map((standard, idx) => (
                          <div
                            key={idx}
                            className="p-4 border-l-4 border-green-400 bg-gradient-to-r from-green-50/50 to-transparent rounded-r-lg hover:shadow-md transition-all duration-200"
                          >
                            <div className="flex items-start justify-between mb-3">
                              <div className="flex-1">
                                <p className="font-mono font-bold text-green-900 text-lg">
                                  {standard.designation}
                                </p>
                                <p className="text-gray-700 mt-1">
                                  {standard.title}
                                </p>
                              </div>
                              <div className="flex gap-2 flex-wrap justify-end">
                                {standard.is_mandatory && (
                                  <Badge className="bg-red-600 text-white font-semibold">
                                    Mandatory
                                  </Badge>
                                )}
                                <Badge className="bg-blue-100 text-blue-900 font-medium">
                                  {standard.role.replace(/_/g, " ")}
                                </Badge>
                              </div>
                            </div>
                            <div className="text-xs font-medium">
                              {standard.why.startsWith("alias:") && (
                                <span className="text-green-700 flex items-center gap-1">
                                  <CheckCircle2 className="w-3 h-3" /> Direct match
                                </span>
                              )}
                              {standard.why.startsWith("hybrid:") && (
                                <span className="text-blue-700 flex items-center gap-1">
                                  <Sparkles className="w-3 h-3" /> Semantic match (confidence: {Math.round((standard.score || 0) * 100)}%)
                                </span>
                              )}
                            </div>
                          </div>
                        ))}
                      </div>
                    </CardContent>
                  </Card>
                )}

                {/* Related Standards Toggle */}
                {result.related?.length > 0 && (
                  <div className="space-y-4">
                    <button
                      onClick={() => setShowRelated(!showRelated)}
                      className="w-full flex items-center justify-between p-4 bg-white/95 backdrop-blur-xl rounded-lg border-0 shadow-lg hover:shadow-xl transition-all duration-200 font-semibold text-gray-900"
                    >
                      <div className="flex items-center gap-3">
                        <Filter className="w-5 h-5 text-indigo-600" />
                        <span>Related Standards ({result.related.length})</span>
                      </div>
                      <span className={`transition-transform duration-200 ${showRelated ? 'rotate-180' : ''}`}>
                        ▼
                      </span>
                    </button>

                    {showRelated && (
                      <Card className="border-0 bg-white/95 backdrop-blur-xl shadow-xl">
                        <CardHeader className="bg-gradient-to-r from-indigo-50 to-blue-50 pb-4">
                          <div className="flex items-center gap-3">
                            <div className="p-2 bg-indigo-200 rounded-lg">
                              <Filter className="w-5 h-5 text-indigo-700" />
                            </div>
                            <div>
                              <CardTitle className="text-indigo-900">Supporting Standards</CardTitle>
                              <p className="text-xs text-indigo-700 mt-1">Test methods, codes, and guidelines</p>
                            </div>
                          </div>
                        </CardHeader>
                        <CardContent className="pt-6">
                          <div className="space-y-2">
                            {result.related.map((standard, idx) => (
                              <div
                                key={idx}
                                className="p-3 border border-indigo-100 rounded-lg hover:bg-indigo-50/50 transition-colors duration-200"
                              >
                                <div className="flex justify-between items-start">
                                  <div>
                                    <p className="font-mono font-semibold text-indigo-900">
                                      {standard.designation}
                                    </p>
                                    <p className="text-gray-700 text-sm">
                                      {standard.title}
                                    </p>
                                  </div>
                                  <Badge className="bg-indigo-100 text-indigo-900 whitespace-nowrap ml-2">
                                    {standard.role.replace(/_/g, " ")}
                                  </Badge>
                                </div>
                              </div>
                            ))}
                          </div>
                        </CardContent>
                      </Card>
                    )}
                  </div>
                )}

                {/* Empty State */}
                {!result.primary?.length && !result.related?.length && (
                  <Card className="border-0 bg-white/95 backdrop-blur-xl shadow-xl">
                    <CardContent className="p-12 text-center">
                      <div className="inline-block p-4 bg-amber-100 rounded-full mb-4">
                        <AlertCircle className="w-8 h-8 text-amber-600" />
                      </div>
                      <p className="text-gray-900 font-semibold mb-2">No standards found</p>
                      <p className="text-gray-600">Try describing your product with more common or specific terms</p>
                    </CardContent>
                  </Card>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      <style jsx>{`
        @keyframes blob {
          0%, 100% { transform: translate(0, 0) scale(1); }
          33% { transform: translate(30px, -50px) scale(1.1); }
          66% { transform: translate(-20px, 20px) scale(0.9); }
        }
        @keyframes fade-in {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .animate-blob {
          animation: blob 7s infinite;
        }
        .animation-delay-2000 {
          animation-delay: 2s;
        }
        .animate-fade-in {
          animation: fade-in 0.5s ease-out;
        }
      `}</style>
    </div>
  );
}
