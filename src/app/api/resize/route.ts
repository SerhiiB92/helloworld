import { NextResponse } from "next/server";
import { getFormat } from "@/lib/formats";
import { fitToFormat, parseDataUrl, type ResizeMode } from "@/lib/image";

export const maxDuration = 30;

// Resize an already-generated image into another format using sharp only
// (no model call): crop ("cover") to fill, or pad ("contain") to letterbox.
export async function POST(request: Request) {
  let body: { image?: string; format?: string; mode?: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { image, format: formatId, mode } = body;

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

  const resizeMode: ResizeMode = mode === "contain" ? "contain" : "cover";

  try {
    const fitted = await fitToFormat(parsed.base64, format, resizeMode);
    return NextResponse.json({
      image: `data:${fitted.mimeType};base64,${fitted.base64}`,
    });
  } catch (error) {
    console.error("Resize failed", error);
    const message = error instanceof Error ? error.message : "Resize failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
