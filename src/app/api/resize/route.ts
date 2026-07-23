import { NextResponse } from "next/server";
import { getFormat } from "@/lib/formats";
import { parseDataUrl } from "@/lib/image";
import { adaptToFormat, describeError } from "@/lib/gemini";

export const maxDuration = 60;

// Re-adapt an already-generated creative into another format. Instead of
// cropping (which cut text off), we ask the model to REDRAW the creative for
// the new aspect ratio so the whole text reflows and stays visible.
export async function POST(request: Request) {
  let body: { image?: string; format?: string; prompt?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { image, format: formatId, prompt } = body;

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

  try {
    const adapted = await adaptToFormat({
      imageBase64: parsed.base64,
      mimeType: parsed.mimeType,
      targetFormat: format,
      originalPrompt: typeof prompt === "string" ? prompt : undefined,
    });
    return NextResponse.json({
      image: `data:${adapted.mimeType};base64,${adapted.imageBase64}`,
    });
  } catch (error) {
    console.error("Resize failed", error);
    return NextResponse.json({ error: describeError(error) }, { status: 502 });
  }
}
