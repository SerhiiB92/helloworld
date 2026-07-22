import sharp from "sharp";
import type { FormatDef } from "./formats";

export type ResizeMode = "cover" | "contain";

// Crop (cover) or pad (contain) a base64 image to a format's exact dimensions.
// "cover" center-crops to fill the frame; "contain" letterboxes with a
// background so nothing is cut off.
export async function fitToFormat(
  imageBase64: string,
  format: FormatDef,
  mode: ResizeMode = "cover",
  background = "#000000",
): Promise<{ base64: string; mimeType: string }> {
  const input = Buffer.from(imageBase64, "base64");

  const output = await sharp(input)
    .resize({
      width: format.width,
      height: format.height,
      fit: mode,
      position: "centre",
      background,
    })
    .png()
    .toBuffer();

  return { base64: output.toString("base64"), mimeType: "image/png" };
}

// Parse a data URL (data:<mime>;base64,<data>) into its parts.
export function parseDataUrl(
  dataUrl: string,
): { base64: string; mimeType: string } | null {
  const match = /^data:([^;]+);base64,([\s\S]+)$/.exec(dataUrl);
  if (!match) return null;
  return { mimeType: match[1], base64: match[2] };
}
