import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, filterQuery, qs, setUnauthorizedHandler } from "./client";

function jsonResponse(body: unknown, status = 200) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

describe("qs / filterQuery", () => {
  it("skips undefined and empty values", () => {
    expect(qs({ a: 1, b: undefined, c: "", d: "x" })).toBe("?a=1&d=x");
    expect(qs({})).toBe("");
  });

  it("includes days and attribution filters", () => {
    expect(filterQuery({ days: 7, project_id: "p1", client_id: undefined, workflow: "checkout" })).toBe(
      "?days=7&project_id=p1&workflow=checkout"
    );
  });
});

describe("api", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    setUnauthorizedHandler(null);
  });

  it("builds execution queries with search/sort/order", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [], total: 0 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.executions(
      { days: 7, project_id: "p1" },
      { q: "refund", sort: "duration_ms", order: "asc", limit: 25, offset: 25 }
    );
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("/executions?");
    expect(url).toContain("days=7");
    expect(url).toContain("project_id=p1");
    expect(url).toContain("q=refund");
    expect(url).toContain("sort=duration_ms");
    expect(url).toContain("order=asc");
    expect(url).toContain("limit=25");
    expect(url).toContain("offset=25");
  });

  it("sends credentials and the CSRF header on mutations", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "b1" }));
    vi.stubGlobal("fetch", fetchMock);
    await api.budgets.create({
      amount: 10,
      period: "2026-01-01",
      period_type: "month",
      team: "t1",
    });
    const [, init] = fetchMock.mock.calls[0];
    expect(init.method).toBe("POST");
    const headers = init.headers as Headers;
    expect(headers.get("x-requested-with")).toBe("aiobs");
    expect(headers.get("content-type")).toBe("application/json");
    expect(init.credentials).toBe("include");
  });

  it("sends PATCH for updates", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id: "b1" }));
    vi.stubGlobal("fetch", fetchMock);
    await api.budgets.update("b1", { amount: 20 });
    expect(fetchMock.mock.calls[0][1].method).toBe("PATCH");
  });

  it("throws ApiError with status on error responses", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({ detail: "nope" }, 409)));
    await expect(api.pricing.remove("x")).rejects.toMatchObject({ status: 409 });
  });

  it("invokes the unauthorized handler on 401", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(jsonResponse({}, 401)));
    await expect(api.alerts.list()).rejects.toBeInstanceOf(ApiError);
    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("returns undefined for 204", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 204 } as unknown as Response)
    );
    await expect(api.alerts.update("a1", "closed")).resolves.toBeUndefined();
  });

  it("encodes alert query params", async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ items: [], total: 0 }));
    vi.stubGlobal("fetch", fetchMock);
    await api.alerts.list({ status: "open", severity: "critical", q: "budget", limit: 50 });
    const url = String(fetchMock.mock.calls[0][0]);
    expect(url).toContain("status=open");
    expect(url).toContain("severity=critical");
    expect(url).toContain("q=budget");
  });
});
