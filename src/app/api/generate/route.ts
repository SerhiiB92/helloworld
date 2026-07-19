import { NextResponse } from "next/server";
import {
  generateEditedImage,
  SUPPORTED_ASPECT_RATIOS,
  type AspectRatio,
} from "@/lib/gemini";

export async function POST(request: Request) {
  const formData = await request.formData();

  const image = formData.get("image");
  const prompt = formData.get("prompt");
  const aspectRatio = formData.get("aspectRatio");

  if (!(image instanceof File)) {
    return NextResponse.json({ error: "Missing image" }, { status: 400 });
  }
  if (typeof prompt !== "string" || prompt.trim().length === 0) {
    return NextResponse.json({ error: "Missing prompt" }, { status: 400 });
  }
  if (
    typeof aspectRatio !== "string" ||
    !SUPPORTED_ASPECT_RATIOS.includes(aspectRatio as AspectRatio)
  ) {
    return NextResponse.json({ error: "Invalid aspect ratio" }, { status: 400 });
  }

  const arrayBuffer = await image.arrayBuffer();
  const imageBase64 = Buffer.from(arrayBuffer).toString("base64");

  try {
    const result = await generateEditedImage({
      imageBase64,
      mimeType: image.type || "image/png",
      prompt,
      aspectRatio: aspectRatio as AspectRatio,
    });

    return NextResponse.json({
      image: `data:${result.mimeType};base64,${result.imageBase64}`,
    });
  } catch (error) {
    console.error("Image generation failed", error);
    const message =
      error instanceof Error ? error.message : "Image generation failed";
    return NextResponse.json({ error: message }, { status: 502 });
  }
}
