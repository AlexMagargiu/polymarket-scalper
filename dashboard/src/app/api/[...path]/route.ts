import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.API_BASE_URL || "http://localhost:8099";
const API_AUTH_TOKEN = process.env.API_AUTH_TOKEN || "";

export async function GET(req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const apiPath = path.join("/");
  const search = req.nextUrl.searchParams.toString();
  const url = `${API_BASE}/api/${apiPath}${search ? "?" + search : ""}`;

  const headers: HeadersInit = {};
  if (API_AUTH_TOKEN) {
    headers["Authorization"] = `Bearer ${API_AUTH_TOKEN}`;
  }

  try {
    const res = await fetch(url, { cache: "no-store", headers });
    if (!res.ok) {
      return NextResponse.json({ error: `API returned ${res.status}` }, { status: res.status });
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "API unreachable" }, { status: 502 });
  }
}

async function proxyWithBody(method: string, req: NextRequest, { params }: { params: Promise<{ path: string[] }> }) {
  const { path } = await params;
  const apiPath = path.join("/");
  const url = `${API_BASE}/api/${apiPath}`;
  const body = await req.text();

  const headers: HeadersInit = { "Content-Type": "application/json" };
  if (API_AUTH_TOKEN) {
    headers["Authorization"] = `Bearer ${API_AUTH_TOKEN}`;
  }

  try {
    const res = await fetch(url, { method, cache: "no-store", headers, body: body || undefined });
    if (!res.ok) {
      return NextResponse.json({ error: `API returned ${res.status}` }, { status: res.status });
    }
    const data = await res.json();
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: "API unreachable" }, { status: 502 });
  }
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody("POST", req, ctx);
}

export async function PUT(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody("PUT", req, ctx);
}

export async function PATCH(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody("PATCH", req, ctx);
}

export async function DELETE(req: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return proxyWithBody("DELETE", req, ctx);
}
