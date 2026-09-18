import { AxiosError } from "axios";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  api,
  API_BASE_URL,
  gapReportUrl,
  getStandard,
  listStandards,
  recommend,
  type ApiErrorBody,
} from "@/lib/api";

/**
 * These run against a stubbed adapter, not a server, so they are deterministic
 * and cover the paths that are hard to trigger against a healthy API: network
 * failure, timeout, and each documented error status.
 */
function respondWith(status: number, body: unknown) {
  return async (config: Record<string, unknown>) => {
    // A network failure: an AxiosError with no `response` at all. That absence
    // is what the client keys on, so the stub has to reproduce it.
    if (status === 0) {
      throw new AxiosError("Network Error", "ERR_NETWORK", config as never);
    }
    const response = {
      data: body,
      status,
      statusText: String(status),
      headers: {},
      config,
    };
    if (status >= 200 && status < 300) return response;
    // Real axios adapters reject non-2xx by calling `settle`. Returning the
    // response object instead -- the obvious way to write this stub -- makes
    // axios resolve a 404 as success and the client's error mapping is never
    // exercised. That mistake is what these tests caught the first time.
    throw new AxiosError(
      `Request failed with status code ${status}`,
      "ERR_BAD_REQUEST",
      config as never,
      null,
      response as never,
    );
  };
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("base URL", () => {
  it("defaults to a relative path so the browser never needs to reach another host", () => {
    // The single most important property of the client. An absolute
    // http://localhost:8000 default works only when the browser happens to be on
    // the same machine as the API, and fails everywhere else with an error that
    // reads like the API is down.
    expect(API_BASE_URL.startsWith("/")).toBe(true);
    expect(API_BASE_URL).not.toContain("localhost");
  });
});

describe("error mapping", () => {
  it("preserves the API's error body verbatim", async () => {
    const body: ApiErrorBody = {
      error: "not_found",
      detail: "'IS 99999' is not in this dataset. It holds 197 of archive.org's ~22,025 standards.",
      request_id: "abc123",
      status_code: 404,
    };
    api.defaults.adapter = respondWith(404, body) as never;

    const error = (await getStandard("IS 99999").catch((e) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(404);
    expect(error.code).toBe("not_found");
    expect(error.requestId).toBe("abc123");
    // The API's message is kept exactly. Replacing it with "Request failed"
    // would throw away the diagnosis the API went to the trouble of producing.
    expect(error.message).toContain("22,025");
  });

  it("turns a network failure into an instruction, not a stack trace", async () => {
    api.defaults.adapter = respondWith(0, null) as never;
    const error = (await listStandards().catch((e) => e)) as ApiError;
    expect(error.code).toBe("network_error");
    expect(error.message).toContain("uvicorn bis_api.main:app");
  });

  it("keeps a 503 as a 503 so the UI can say the data is missing", async () => {
    api.defaults.adapter = respondWith(503, {
      error: "service_unavailable",
      detail: "bis_data/ is not loaded, so there is nothing to search.",
      request_id: "r1",
      status_code: 503,
    }) as never;
    const error = (await listStandards().catch((e) => e)) as ApiError;
    expect(error.status).toBe(503);
    expect(error.code).toBe("service_unavailable");
  });

  it("survives an error response with no recognisable body", async () => {
    api.defaults.adapter = respondWith(500, "plain text, not JSON") as never;
    const error = (await listStandards().catch((e) => e)) as ApiError;
    expect(error.status).toBe(500);
    expect(error.message.length).toBeGreaterThan(0);
  });
});

describe("success paths", () => {
  it("returns the parsed body unchanged", async () => {
    const payload = { total: 197, returned: 1, standards: [] };
    api.defaults.adapter = respondWith(200, payload) as never;
    await expect(listStandards()).resolves.toEqual(payload);
  });

  it("sends POST bodies as JSON", async () => {
    let seen: unknown;
    api.defaults.adapter = (async (config: { data?: unknown }) => {
      seen = typeof config.data === "string" ? JSON.parse(config.data) : config.data;
      return { data: { answer: "ok" }, status: 200, statusText: "OK", headers: {}, config };
    }) as never;

    await recommend({ query: "IS 269", top_k: 3 });
    expect(seen).toEqual({ query: "IS 269", top_k: 3 });
  });
});

describe("gapReportUrl", () => {
  it("is relative, so it resolves against whatever origin the app is served from", () => {
    expect(gapReportUrl("cement", ["IS 269:1989"]).startsWith("/")).toBe(true);
  });

  it("encodes the product and repeats the standard parameter", () => {
    const url = gapReportUrl("33 grade cement", ["IS 269:1989", "IS 456:2000"]);
    expect(url).toContain("product=33+grade+cement");
    expect(url).toContain("standard=IS+269%3A1989");
    expect(url).toContain("standard=IS+456%3A2000");
  });
});
