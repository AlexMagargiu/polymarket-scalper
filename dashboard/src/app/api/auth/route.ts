import { NextRequest, NextResponse } from "next/server";
import { SignJWT } from "jose";
import { compare } from "bcryptjs";

const JWT_SECRET = new TextEncoder().encode(process.env.JWT_SECRET || "dev-secret-change-in-prod");
const PASSWORD_HASH = process.env.PASSWORD_HASH || "";

export async function POST(req: NextRequest) {
  const { password } = await req.json();

  if (!PASSWORD_HASH) {
    return NextResponse.json({ error: "No password configured" }, { status: 500 });
  }

  const valid = await compare(password, PASSWORD_HASH);
  if (!valid) {
    return NextResponse.json({ error: "Invalid password" }, { status: 401 });
  }

  const token = await new SignJWT({ role: "admin" })
    .setProtectedHeader({ alg: "HS256" })
    .setExpirationTime("7d")
    .sign(JWT_SECRET);

  const res = NextResponse.json({ ok: true });
  res.cookies.set("auth-token", token, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 7,
    path: "/",
  });

  return res;
}
