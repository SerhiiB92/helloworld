// Central definition of every output format the app supports.
// Both the UI and the API import from here so they never drift apart.

export interface SafeZone {
  // Margins in pixels measured against the format's width/height below.
  top: number;
  bottom: number;
  left: number;
  right: number;
}

export interface FormatDef {
  id: string;
  label: string;
  // Final pixel dimensions the user gets.
  width: number;
  height: number;
  // Closest aspect ratio Gemini supports natively for generation.
  // Supported by the model: 1:1, 2:3, 3:2, 3:4, 4:3, 9:16, 16:9, 21:9.
  geminiAspectRatio: string;
  // If the model's native ratio differs from width/height, we crop/pad
  // to the exact dimensions after generation.
  needsPostProcess: boolean;
  // Optional Reels/Stories safe zone the model must respect.
  safeZone?: SafeZone;
  hint?: string;
}

export const FORMATS: FormatDef[] = [
  {
    id: "1:1",
    label: "1:1",
    width: 1080,
    height: 1080,
    geminiAspectRatio: "1:1",
    needsPostProcess: false,
    hint: "Feed / Marketplace",
  },
  {
    id: "4:5",
    label: "4:5",
    width: 1080,
    height: 1350,
    // Model has no 4:5; 3:4 (0.75) is the closest to 4:5 (0.8).
    geminiAspectRatio: "3:4",
    needsPostProcess: true,
    hint: "Feed portrait",
  },
  {
    id: "9:16",
    label: "9:16",
    width: 1080,
    height: 1920,
    geminiAspectRatio: "9:16",
    needsPostProcess: false,
    hint: "Reels / Stories",
  },
  {
    id: "9:16-safe",
    label: "9:16 safe",
    width: 1080,
    height: 1920,
    geminiAspectRatio: "9:16",
    needsPostProcess: false,
    hint: "Reels safe zone",
    // Keep all key content inside this box for Reels/Stories.
    safeZone: { top: 270, bottom: 672, left: 65, right: 65 },
  },
  {
    id: "16:9",
    label: "16:9",
    width: 1920,
    height: 1080,
    geminiAspectRatio: "16:9",
    needsPostProcess: false,
    hint: "Landscape",
  },
];

export const FORMAT_IDS = FORMATS.map((f) => f.id);
export type FormatId = (typeof FORMATS)[number]["id"];

export function getFormat(id: string): FormatDef | undefined {
  return FORMATS.find((f) => f.id === id);
}

// Approximate price per generated image (USD), shown in the UI.
// Rough estimate for Nano Banana Pro (gemini-3-pro-image-preview) — verify
// the real cost in Google AI Studio usage.
export const PRICE_PER_IMAGE = 0.134;
export const MAX_COUNT = 8;
