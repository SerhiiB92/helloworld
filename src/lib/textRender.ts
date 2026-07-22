import path from "path";
import {
  createCanvas,
  loadImage,
  GlobalFonts,
  type SKRSContext2D,
} from "@napi-rs/canvas";
import type { FormatDef } from "./formats";

// --- Font registration (once per process) -------------------------------
let fontsReady = false;
const FONT_BOLD = "CreativeBold";
const FONT_REGULAR = "CreativeRegular";

function ensureFonts() {
  if (fontsReady) return;
  const dir = path.join(process.cwd(), "public", "fonts");
  GlobalFonts.registerFromPath(
    path.join(dir, "DejaVuSans-Bold.ttf"),
    FONT_BOLD,
  );
  GlobalFonts.registerFromPath(path.join(dir, "DejaVuSans.ttf"), FONT_REGULAR);
  fontsReady = true;
}

// --- Public types --------------------------------------------------------
export interface TextConfig {
  headline?: string;
  body?: string;
  price?: string;
  cta?: string;
  accentColor: string; // price circle + CTA button
  textColor: string; // headline/body/price text
}

// --- Helpers -------------------------------------------------------------
function wrapText(
  ctx: SKRSContext2D,
  text: string,
  maxWidth: number,
): string[] {
  const lines: string[] = [];
  // Respect explicit line breaks, then wrap each paragraph by width.
  for (const paragraph of text.split(/\r?\n/)) {
    const words = paragraph.split(/\s+/).filter(Boolean);
    if (words.length === 0) {
      lines.push("");
      continue;
    }
    let current = words[0];
    for (let i = 1; i < words.length; i++) {
      const candidate = `${current} ${words[i]}`;
      if (ctx.measureText(candidate).width <= maxWidth) {
        current = candidate;
      } else {
        lines.push(current);
        current = words[i];
      }
    }
    lines.push(current);
  }
  return lines;
}

function pickContrast(hex: string): string {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex);
  if (!m) return "#ffffff";
  const n = parseInt(m[1], 16);
  const r = (n >> 16) & 255;
  const g = (n >> 8) & 255;
  const b = n & 255;
  // Relative luminance; dark background -> white text and vice versa.
  const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
  return lum > 0.6 ? "#111111" : "#ffffff";
}

function roundedRect(
  ctx: SKRSContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

// A measured, ready-to-draw block.
interface Block {
  type: "headline" | "body" | "price" | "cta";
  lines: string[];
  fontSize: number;
  lineHeight: number;
  font: string;
  height: number;
}

// --- Main API ------------------------------------------------------------
// Composite the given text blocks over a background image, laid out as an
// auto-template centered inside the format's safe zone (or a default margin).
export async function composeCreative(
  backgroundBase64: string,
  format: FormatDef,
  text: TextConfig,
): Promise<{ base64: string; mimeType: string }> {
  ensureFonts();

  const W = format.width;
  const H = format.height;
  const canvas = createCanvas(W, H);
  const ctx = canvas.getContext("2d");

  // 1. Background (cover-fit into the exact frame).
  const bg = await loadImage(Buffer.from(backgroundBase64, "base64"));
  const scale = Math.max(W / bg.width, H / bg.height);
  const dw = bg.width * scale;
  const dh = bg.height * scale;
  ctx.drawImage(bg, (W - dw) / 2, (H - dh) / 2, dw, dh);

  // 2. Content box = safe zone if defined, else 8% padding.
  const sz = format.safeZone;
  const box = sz
    ? { x: sz.left, y: sz.top, w: W - sz.left - sz.right, h: H - sz.top - sz.bottom }
    : { x: W * 0.08, y: H * 0.08, w: W * 0.84, h: H * 0.84 };

  const accent = text.accentColor || "#22c55e";
  const color = text.textColor || "#ffffff";

  // 3. Measure blocks.
  const blocks: Block[] = [];
  const measure = (
    type: Block["type"],
    value: string | undefined,
    fontSize: number,
    font: string,
  ) => {
    if (!value || !value.trim()) return;
    ctx.font = `${fontSize}px ${font}`;
    const lines = wrapText(ctx, value.trim(), box.w * 0.96);
    const lineHeight = fontSize * 1.18;
    blocks.push({
      type,
      lines,
      fontSize,
      lineHeight,
      font,
      height: lines.length * lineHeight,
    });
  };

  measure("headline", text.headline, Math.round(box.w * 0.085), FONT_BOLD);
  measure("body", text.body, Math.round(box.w * 0.045), FONT_REGULAR);
  measure("price", text.price, Math.round(box.w * 0.08), FONT_BOLD);

  // CTA is a single-line button: shrink the font so it always fits the box.
  if (text.cta && text.cta.trim()) {
    const label = text.cta.trim().replace(/\s+/g, " ");
    let ctaSize = Math.round(box.w * 0.05);
    const avail = box.w * 0.84; // leave room for button padding
    ctx.font = `${ctaSize}px ${FONT_BOLD}`;
    const w = ctx.measureText(label).width;
    if (w > avail) ctaSize = Math.max(12, Math.floor((ctaSize * avail) / w));
    const padY = ctaSize * 0.55;
    const buttonHeight = ctaSize + padY * 2;
    blocks.push({
      type: "cta",
      lines: [label],
      fontSize: ctaSize,
      lineHeight: buttonHeight,
      font: FONT_BOLD,
      height: buttonHeight,
    });
  }

  const gap = box.w * 0.06;
  const totalHeight =
    blocks.reduce((s, b) => s + b.height, 0) + gap * Math.max(0, blocks.length - 1);

  let y = box.y + Math.max(0, (box.h - totalHeight) / 2);
  const cx = box.x + box.w / 2;

  ctx.textAlign = "center";
  ctx.textBaseline = "top";

  // 4. Draw blocks.
  for (const b of blocks) {
    if (b.type === "cta") {
      // Rounded button filled with the accent color.
      ctx.font = `${b.fontSize}px ${b.font}`;
      const label = b.lines.join(" ");
      const textW = ctx.measureText(label).width;
      const padX = b.fontSize * 0.7;
      const padY = b.fontSize * 0.55;
      const bw = Math.min(box.w, textW + padX * 2);
      const bh = b.fontSize + padY * 2;
      const bx = cx - bw / 2;
      ctx.save();
      ctx.shadowColor = "rgba(0,0,0,0.35)";
      ctx.shadowBlur = b.fontSize * 0.4;
      ctx.shadowOffsetY = b.fontSize * 0.12;
      ctx.fillStyle = accent;
      roundedRect(ctx, bx, y, bw, bh, bh / 2);
      ctx.fill();
      ctx.restore();
      ctx.fillStyle = pickContrast(accent);
      ctx.fillText(label, cx, y + padY);
      y += bh + gap;
      continue;
    }

    ctx.font = `${b.fontSize}px ${b.font}`;
    ctx.save();
    ctx.shadowColor = "rgba(0,0,0,0.55)";
    ctx.shadowBlur = b.fontSize * 0.35;
    ctx.shadowOffsetY = b.fontSize * 0.06;
    ctx.fillStyle = color;
    let ly = y;
    for (const line of b.lines) {
      ctx.fillText(line, cx, ly);
      ly += b.lineHeight;
    }
    ctx.restore();

    if (b.type === "price") {
      // Ellipse "hand-drawn" circle around the price line.
      const priceW = Math.max(
        ...b.lines.map((l) => ctx.measureText(l).width),
      );
      const rx = priceW / 2 + b.fontSize * 0.5;
      const ry = b.height / 2 + b.fontSize * 0.35;
      const ccx = cx;
      const ccy = y + b.height / 2;
      ctx.save();
      ctx.strokeStyle = accent;
      ctx.lineWidth = Math.max(4, b.fontSize * 0.07);
      ctx.beginPath();
      ctx.ellipse(ccx, ccy, rx, ry, -0.05, 0, Math.PI * 2);
      ctx.stroke();
      ctx.restore();
    }

    y += b.height + gap;
  }

  const png = canvas.toBuffer("image/png");
  return { base64: png.toString("base64"), mimeType: "image/png" };
}
