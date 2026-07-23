import { NextResponse } from "next/server";
import { generateVariants, describeError } from "@/lib/gemini";
import { getFormat, MAX_COUNT } from "@/lib/formats";

export const maxDuration = 60;

export async function POST(request: Request) {
  const formData = await request.formData();

  const image = formData.get("image");
  const prompt = formData.get("prompt");
  const formatId = formData.get("format");
  const removeLogos = formData.get("removeLogos") === "true";
  const removeWatermarks = formData.get("removeWatermarks") === "true";
  const cleanBackground = formData.get("cleanBackground") === "true";
  const count = Number(formData.get("count") ?? "1");

  if (!(image instanceof File)) {
    return NextResponse.json({ error: "Missing image" }, { status: 400 });
  }
  if (typeof prompt !== "string") {
    return NextResponse.json({ error: "Missing prompt" }, { status: 400 });
  }
  const format = typeof formatId === "string" ? getFormat(formatId) : undefined;
  if (!format) {
    return NextResponse.json({ error: "Invalid format" }, { status: 400 });
  }
  if (!Number.isInteger(count) || count < 1 || count > MAX_COUNT) {
    return NextResponse.json({ error: "Invalid count" }, { status: 400 });
  }

  const arrayBuffer = await image.arrayBuffer();
  const imageBase64 = Buffer.from(arrayBuffer).toString("base64");

  try {
    const results = await generateVariants(
      {
        imageBase64,
        mimeType: image.type || "image/png",
        prompt,
        format,
        removeLogos,
        removeWatermarks,
        cleanBackground,
      },
      count,
    );

    return NextResponse.json({
      images: results.map(
        (r) => `data:${r.mimeType};base64,${r.imageBase64}`,
      ),
    });
  } catch (error) {
    console.error("Image generation failed", error);
    return NextResponse.json({ error: describeError(error) }, { status: 502 });
  }
}
