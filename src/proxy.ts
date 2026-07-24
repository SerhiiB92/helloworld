import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

// Password gate for the whole app (pages AND /api/*), so the public deployment
// can't be used by strangers to spend the Gemini API budget.
//
// In Next.js 16 this file is called `proxy` (formerly `middleware`); the
// behaviour is the same — it runs on the server before every matched request.
//
// Configure on Vercel (Settings → Environment Variables):
//   APP_PASSWORD  — required to turn the gate ON. If it is empty/unset the app
//                   stays open exactly as before (so you can't lock yourself
//                   out by forgetting to set it).
//   APP_USER      — optional username for the browser login dialog (default
//                   "admin"). The password is what actually matters.

function unauthorized(): NextResponse {
  return new NextResponse("Authentication required", {
    status: 401,
    headers: {
      "WWW-Authenticate": 'Basic realm="Restricted", charset="UTF-8"',
    },
  });
}

export function proxy(request: NextRequest): NextResponse {
  const password = process.env.APP_PASSWORD;

  // Gate disabled when no password is configured — app behaves as before.
  if (!password) return NextResponse.next();

  const expectedUser = process.env.APP_USER || "admin";

  const header = request.headers.get("authorization");
  if (header?.startsWith("Basic ")) {
    try {
      // "Basic base64(user:pass)" → "user:pass"
      const decoded = atob(header.slice(6));
      const sep = decoded.indexOf(":");
      const user = decoded.slice(0, sep);
      const pass = decoded.slice(sep + 1);
      if (user === expectedUser && pass === password) {
        return NextResponse.next();
      }
    } catch {
      // Malformed header → fall through to 401.
    }
  }

  return unauthorized();
}

export const config = {
  // Run on everything except Next's static assets and the favicon, so CSS/JS
  // and images still load on the login screen.
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
