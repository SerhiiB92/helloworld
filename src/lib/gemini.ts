import { GoogleGenAI } from "@google/genai";
import type { FormatDef } from "./formats";
import { fitToFormat } from "./image";

const MODEL = process.env.GEMINI_MODEL ?? "gemini-3-pro-image-preview";

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

// Shared instructions for keeping key content inside the Reels/Stories safe
// zone, appended to any prompt whose target format defines one.
function safeZoneInstruction(format: FormatDef): string | null {
  const sz = format.safeZone;
  if (!sz) return null;
  const { width, height } = format;
  return [
    `This is a ${width}x${height}px vertical ad creative for Facebook/Instagram Reels.`,
    `Keep every important element — headline, face, product, logo and CTA — strictly inside the safe zone:`,
    `top margin ${sz.top}px, bottom margin ${sz.bottom}px, left and right margins ${sz.left}px.`,
    `Do NOT place important text, buttons, logos or faces in the top, bottom or side margins, because they may be covered by the Reels/Stories interface.`,
  ].join(" ");
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

  // Always ask the model to keep the full text inside the frame — this is the
  // single most common failure (text touching or bleeding past the edges).
  parts.push(
    "Keep ALL text fully inside the frame with comfortable margins; nothing should be cropped, cut off, or touch the edges. Scale the text so the whole message fits and reads clearly at this aspect ratio.",
  );

  const sz = safeZoneInstruction(opts.format);
  if (sz) parts.push(sz);

  return parts.join("\n\n");
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

// The Pro model throttles under load with 503/UNAVAILABLE. Retry ONLY those
// genuinely transient overload errors. Do NOT retry 429/RESOURCE_EXHAUSTED
// spend-based rate limits: they won't clear in seconds and each retry spends
// more budget, making the limit worse.
function isTransient(err: unknown): boolean {
  const msg = err instanceof Error ? err.message : String(err);
  if (/spend-based|spending rate|billing/i.test(msg)) return false;
  return /\b(503|UNAVAILABLE|overloaded|high demand)\b/i.test(msg);
}

// Turn a raw model/SDK error into a clear, actionable message (in Russian for
// the UI). Keeps users out of the "not valid JSON" / raw-Google-JSON weeds.
export function describeError(err: unknown): string {
  const msg = err instanceof Error ? err.message : String(err);
  if (/spend-based|spending rate/i.test(msg)) {
    return "Google ограничил скорость трат по вашему аккаунту (spend-based rate limit). Это лимит аккаунта, а не ошибка приложения: подождите минуту, генерируйте по одному варианту за раз, либо повысьте лимит/тариф в Google AI Studio → Billing.";
  }
  if (/\b(503|UNAVAILABLE|overloaded|high demand)\b/i.test(msg)) {
    return "Модель Nano Banana Pro сейчас перегружена (503). Мы уже пробовали несколько раз — подождите несколько секунд и попробуйте снова.";
  }
  if (/\b429\b|RESOURCE_EXHAUSTED/i.test(msg)) {
    return "Превышен лимит запросов Google (429). Подождите немного и попробуйте снова, либо уменьшите количество вариантов.";
  }
  if (/API key|GEMINI_API_KEY|API_KEY_INVALID|permission|PERMISSION_DENIED/i.test(msg)) {
    return "Проблема с ключом Gemini API. Проверьте переменную GEMINI_API_KEY в настройках окружения Vercel.";
  }
  if (/did not return an image/i.test(msg)) {
    return "Модель не вернула картинку (возможно, отклонила запрос). Переформулируйте промт или попробуйте снова.";
  }
  return msg;
}

// One model call to image, with bounded retry on transient overload only.
// The retry budget is kept small (max ~4.5s of sleeps) so several parallel
// calls still finish within the serverless function's time limit.
async function callModel(
  mimeType: string,
  imageBase64: string,
  prompt: string,
  aspectRatio: string,
): Promise<string> {
  const ai = getClient();

  const maxAttempts = 3;
  let response;
  for (let attempt = 1; ; attempt++) {
    try {
      response = await ai.models.generateContent({
        model: MODEL,
        contents: [
          {
            role: "user",
            parts: [
              { inlineData: { mimeType, data: imageBase64 } },
              { text: prompt },
            ],
          },
        ],
        config: {
          responseModalities: ["IMAGE"],
          imageConfig: { aspectRatio },
        },
      });
      break;
    } catch (err) {
      if (attempt >= maxAttempts || !isTransient(err)) throw err;
      // 1.5s, 3s backoff.
      await sleep(1500 * 2 ** (attempt - 1));
    }
  }

  const responseParts = response.candidates?.[0]?.content?.parts ?? [];
  const imagePart = responseParts.find((p) => p.inlineData?.data);
  if (!imagePart?.inlineData?.data) {
    throw new Error("Model did not return an image");
  }
  return imagePart.inlineData.data;
}

async function generateOne(
  opts: GenerateOptions,
  prompt: string,
): Promise<GeneratedImage> {
  const rawBase64 = await callModel(
    opts.mimeType,
    opts.imageBase64,
    prompt,
    opts.format.geminiAspectRatio,
  );

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

export interface AdaptOptions {
  // The already-generated creative (data stripped to raw base64).
  imageBase64: string;
  mimeType: string;
  // Format we want to re-lay-out the creative into.
  targetFormat: FormatDef;
  // The original brief, so text content stays identical after re-layout.
  originalPrompt?: string;
}

// Re-compose an existing creative into another aspect ratio by asking the
// model to REDRAW it — reflowing and rescaling the text so the whole message
// fits the new frame. This replaces the old sharp crop, which simply cut off
// whatever text fell outside the new box.
export async function adaptToFormat(
  opts: AdaptOptions,
): Promise<GeneratedImage> {
  const f = opts.targetFormat;
  const parts: string[] = [
    `Re-adapt this existing ad creative to a ${f.width}x${f.height}px canvas (aspect ratio ${f.id}).`,
    "Keep the SAME design language: colors, fonts, style, background feel and every piece of text content.",
    "Do NOT simply crop or letterbox. Recompose the layout natively for the new proportions: reflow and rescale the headline, body copy, price and button so the ENTIRE text is fully visible with comfortable margins and nothing is cut off or touches the edges.",
    "The result must look purpose-made for this size, balanced and professional.",
  ];

  if (opts.originalPrompt?.trim()) {
    parts.push(
      `Keep this exact text/brief:\n${opts.originalPrompt.trim()}`,
    );
  }

  const sz = safeZoneInstruction(f);
  if (sz) parts.push(sz);

  const rawBase64 = await callModel(
    opts.mimeType,
    opts.imageBase64,
    parts.join("\n\n"),
    f.geminiAspectRatio,
  );

  const fitted = await fitToFormat(rawBase64, f, "cover");
  return { imageBase64: fitted.base64, mimeType: fitted.mimeType };
}
