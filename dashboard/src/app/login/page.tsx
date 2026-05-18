"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      const res = await fetch("/api/auth", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });

      if (!res.ok) {
        setError("Invalid password");
        return;
      }

      router.push("/");
      router.refresh();
    } catch {
      setError("Connection error");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-base">
      <Card className="w-full max-w-sm border-border-glass bg-raised">
        <CardHeader className="text-center">
          <CardTitle className="text-2xl font-bold text-text-primary">
            Polymarket Scalper
          </CardTitle>
          <p className="text-sm text-text-secondary">Dashboard Login</p>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="bg-surface border-border-glass text-text-primary"
              autoFocus
            />
            {error && (
              <p className="text-sm text-status-loss text-center">{error}</p>
            )}
            <Button
              type="submit"
              disabled={loading || !password}
              className="w-full font-semibold text-[#030711] cursor-pointer"
              style={{
                background: "linear-gradient(135deg, #4DA3FF, #00C48F)",
              }}
            >
              {loading ? "Signing in..." : "Sign In"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
