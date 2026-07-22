import { NextResponse } from "next/server";
import { getFormat } from "@/lib/formats";
import { parseDataUrl } from "@/lib/image";
import { composeCreative, type TextConfig } from "@/lib/textRender";

export const maxDuration = 30;

// Overlay exact, crisp text (real font, not model-painted) onto a generated
// background. No model call — fast and re-runnable when the text changes.
export async function POST(request: Request) {
  let body: {
    image?: string;
    format?: string;
    text?: Partial<TextConfig>;
  };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { image, format: formatId, text } = body;

  if (typeof image !== "string") {
    return NextResponse.json({ error: "Missing image" }, { status: 400 });
  }
  const format = typeof formatId === "string" ? getFormat(formatId) : undefined;
  if (!format) {
    return NextResponse.json({ error: "Invalid format" }, { status: 400 });
  }
  const parsed = parseDataUrl(image);
  if (!parsed) {
    return NextResponse.json({ error: "Invalid image data" }, { status: 400 });
  }

  const config: TextConfig = {
    headline: text?.headline,
    body: text?.body,
    price: text?.price,
    cta: text?.cta,
    accentColor: text?.accentColor || "#22c55e",
    textColor: text?.textColor || "#ffffff",
  };

  try {
    const out = await composeCreative(parsed.base64, format, config);
    return NextResponse.json({
      image: `data:${out.mimeType};base64,${out.base64}`,
    });
  } catch (error) {
    console.error("Compose failed", error);
    const message = error instanceof Error ? error.message : "Compose failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
