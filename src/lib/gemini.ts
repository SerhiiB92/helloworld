import { GoogleGenAI } from "@google/genai";
import type { FormatDef } from "./formats";
import { fitToFormat } from "./image";

const MODEL = process.env.GEMINI_MODEL ?? "gemini-2.5-flash-image";

let client: GoogleGenAI | null = null;

function getClient(): GoogleGenAI {
  if (client) return client;

  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error("GEMINI_API_KEY is not set");
  }
  client = new GoogleGenAI({ apiKey });
  return client;
}

export interface GenerateOptions {
  imageBase64: string;
  mimeType: string;
  prompt: string;
  format: FormatDef;
  removeLogos: boolean;
  removeWatermarks: boolean;
  // When true, ask the model to produce a text-free background so that exact
  // text can be composited on top afterwards.
  cleanBackground: boolean;
}

export interface GeneratedImage {
  imageBase64: string;
  mimeType: string;
}

// Assemble the full instruction sent to the model, layering the user prompt
// with the requested clean-up and safe-zone rules.
export function buildPrompt(opts: GenerateOptions): string {
  const parts: string[] = [];

  if (opts.prompt.trim()) {
    parts.push(opts.prompt.trim());
  }

  if (opts.removeLogos) {
    parts.push(
      "Remove any logos, brand marks and icons from the image, and reconstruct the underlying background naturally so no trace remains.",
    );
  }
  if (opts.removeWatermarks) {
    parts.push(
      "Remove any watermarks, stamps or overlaid semi-transparent text, and reconstruct the underlying background naturally.",
    );
  }

  if (opts.cleanBackground) {
    parts.push(
      "Do NOT render any text, letters, numbers, captions or typography anywhere in the image. Produce a clean background image with calm, uncluttered areas where text can later be overlaid. Keep the composition balanced and leave visual breathing room.",
    );
  }

  const sz = opts.format.safeZone;
  if (sz) {
    const { width, height } = opts.format;
    parts.push(
      [
        `Produce a ${width}x${height}px vertical ad creative for Facebook/Instagram Reels.`,
        `Keep every important element — headline, face, product, logo and CTA — strictly inside the safe zone:`,
        `top margin ${sz.top}px, bottom margin ${sz.bottom}px, left and right margins ${sz.left}px.`,
        `Do NOT place important text, buttons, logos or faces in the top, bottom or side margins, because they may be covered by the Reels/Stories interface.`,
      ].join(" "),
    );
  }

  return parts.join("\n\n");
}

async function generateOne(
  opts: GenerateOptions,
  prompt: string,
): Promise<GeneratedImage> {
  const ai = getClient();

  const response = await ai.models.generateContent({
    model: MODEL,
    contents: [
      {
        role: "user",
        parts: [
          { inlineData: { mimeType: opts.mimeType, data: opts.imageBase64 } },
          { text: prompt },
        ],
      },
    ],
    config: {
      responseModalities: ["IMAGE"],
      imageConfig: { aspectRatio: opts.format.geminiAspectRatio },
    },
  });

  const responseParts = response.candidates?.[0]?.content?.parts ?? [];
  const imagePart = responseParts.find((p) => p.inlineData?.data);

  if (!imagePart?.inlineData?.data) {
    throw new Error("Model did not return an image");
  }

  const rawBase64 = imagePart.inlineData.data;

  // The model returns its own native resolution (and, for 4:5, a nearby
  // ratio). Always fit to the format's exact pixel dimensions so creatives
  // come out at spec (e.g. 1080x1920). For matching ratios this is a clean
  // scale; for 4:5 it also center-crops the small ratio difference.
  const fitted = await fitToFormat(rawBase64, opts.format, "cover");

  return { imageBase64: fitted.base64, mimeType: fitted.mimeType };
}

// Generate `count` variants in parallel.
export async function generateVariants(
  opts: GenerateOptions,
  count: number,
): Promise<GeneratedImage[]> {
  const prompt = buildPrompt(opts);
  const jobs = Array.from({ length: count }, () => generateOne(opts, prompt));
  return Promise.all(jobs);
}
