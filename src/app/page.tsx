"use client";

import { useMemo, useState } from "react";
import { FORMATS, getFormat, MAX_COUNT, PRICE_PER_IMAGE } from "@/lib/formats";

interface ResizeItem {
  id: string;
  formatId: string;
  src: string | null;
  loading: boolean;
  error: string | null;
}

interface Variant {
  id: string;
  src: string;
  formatId: string;
  // The prompt used to generate this variant, reused when re-adapting it to
  // another format so the text content stays identical.
  prompt: string;
  menuOpen: boolean;
  resizes: ResizeItem[];
}

function uid() {
  return Math.random().toString(36).slice(2) + Date.now().toString(36);
}

// Read a fetch Response as JSON, but survive non-JSON bodies (e.g. a Vercel
// platform timeout page for the slow Pro model) with a clear message instead
// of a raw "Unexpected token ... is not valid JSON" crash.
async function readJson(res: Response): Promise<{ [k: string]: unknown }> {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    if (res.status === 504 || /timed out|timeout|FUNCTION_INVOCATION/i.test(text)) {
      throw new Error(
        "Сервер не успел ответить — модель Pro рисует долго. Уменьшите количество вариантов и попробуйте снова.",
      );
    }
    throw new Error(
      res.ok
        ? "Некорректный ответ сервера."
        : `Ошибка сервера (${res.status}). Модель Pro могла не успеть ответить — попробуйте ещё раз.`,
    );
  }
}

function ImageFrame({ src, alt }: { src: string; alt: string }) {
  return (
    <div className="relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-900 dark:border-zinc-800">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={src} alt={alt} className="w-full object-contain" />
    </div>
  );
}

function VariantCard({
  variant,
  onToggleMenu,
  onResize,
}: {
  variant: Variant;
  onToggleMenu: (id: string) => void;
  onResize: (id: string, formatId: string) => void;
}) {
  const format = getFormat(variant.formatId);
  return (
    <div className="flex items-start gap-3">
      <div className="w-56 shrink-0">
        <ImageFrame src={variant.src} alt="Сгенерированный вариант" />
        <div className="mt-2 flex items-center justify-between">
          <span className="text-xs text-zinc-500">{format?.label}</span>
          <div className="flex gap-2">
            <a
              href={variant.src}
              download={`variant-${variant.id}.png`}
              className="text-xs text-zinc-600 hover:text-orange-600 dark:text-zinc-400"
            >
              Скачать
            </a>
            <button
              type="button"
              onClick={() => onToggleMenu(variant.id)}
              className="text-xs text-zinc-600 hover:text-orange-600 dark:text-zinc-400"
            >
              Ресайз
            </button>
          </div>
        </div>
        {variant.menuOpen && (
          <div className="mt-2 rounded-md border border-zinc-200 p-2 dark:border-zinc-800">
            <p className="mb-1.5 text-[11px] text-zinc-500">
              Перерисовать в формат (модель переверстает текст, ~$
              {PRICE_PER_IMAGE} и до минуты):
            </p>
            <div className="flex flex-wrap gap-1.5">
              {FORMATS.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => onResize(variant.id, f.id)}
                  className="rounded-md border border-zinc-300 px-2 py-1 text-xs text-zinc-700 transition-colors hover:border-orange-500 hover:text-orange-600 dark:border-zinc-700 dark:text-zinc-300"
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {variant.resizes.map((r) => (
        <div key={r.id} className="w-56 shrink-0">
          <div className="flex min-h-40 items-center justify-center rounded-lg border border-dashed border-zinc-300 bg-white dark:border-zinc-700 dark:bg-zinc-900">
            {r.loading && (
              <span className="text-xs text-zinc-500">Перерисовываю...</span>
            )}
            {!r.loading && r.error && (
              <span className="px-2 text-center text-xs text-red-500">
                {r.error}
              </span>
            )}
            {!r.loading && r.src && <ImageFrame src={r.src} alt="Ресайз" />}
          </div>
          {!r.loading && r.src && (
            <div className="mt-2 flex items-center justify-between">
              <span className="text-xs text-zinc-500">
                {getFormat(r.formatId)?.label}
              </span>
              <a
                href={r.src}
                download={`resize-${r.id}.png`}
                className="text-xs text-zinc-600 hover:text-orange-600 dark:text-zinc-400"
              >
                Скачать
              </a>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [formatId, setFormatId] = useState<string>("9:16");
  const [removeLogos, setRemoveLogos] = useState(true);
  const [removeWatermarks, setRemoveWatermarks] = useState(true);
  const [count, setCount] = useState(1);
  const [variants, setVariants] = useState<Variant[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedFormat = useMemo(() => getFormat(formatId), [formatId]);
  const cost = (count * PRICE_PER_IMAGE).toFixed(3);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    setFile(selected);
    setError(null);
    setPreviewUrl(selected ? URL.createObjectURL(selected) : null);
  }

  async function handleGenerate() {
    if (!file) return;
    setIsLoading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("image", file);
      formData.append("prompt", prompt);
      formData.append("format", formatId);
      formData.append("removeLogos", String(removeLogos));
      formData.append("removeWatermarks", String(removeWatermarks));
      formData.append("count", String(count));

      const res = await fetch("/api/generate", {
        method: "POST",
        body: formData,
      });
      const data = await readJson(res);
      if (!res.ok) throw new Error((data.error as string) ?? "Generation failed");

      const newVariants: Variant[] = (data.images as string[]).map((src) => ({
        id: uid(),
        src,
        formatId,
        prompt,
        menuOpen: false,
        resizes: [],
      }));
      setVariants((prev) => [...newVariants, ...prev]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setIsLoading(false);
    }
  }

  function toggleMenu(id: string) {
    setVariants((prev) =>
      prev.map((v) => (v.id === id ? { ...v, menuOpen: !v.menuOpen } : v)),
    );
  }

  async function handleResize(variantId: string, targetFormat: string) {
    const variant = variants.find((v) => v.id === variantId);
    if (!variant) return;

    const resizeId = uid();
    setVariants((prev) =>
      prev.map((v) =>
        v.id === variantId
          ? {
              ...v,
              menuOpen: false,
              resizes: [
                ...v.resizes,
                {
                  id: resizeId,
                  formatId: targetFormat,
                  src: null,
                  loading: true,
                  error: null,
                },
              ],
            }
          : v,
      ),
    );

    try {
      const res = await fetch("/api/resize", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          image: variant.src,
          format: targetFormat,
          prompt: variant.prompt,
        }),
      });
      const data = await readJson(res);
      if (!res.ok) throw new Error((data.error as string) ?? "Resize failed");

      setVariants((prev) =>
        prev.map((v) =>
          v.id === variantId
            ? {
                ...v,
                resizes: v.resizes.map((r) =>
                  r.id === resizeId
                    ? { ...r, loading: false, src: data.image as string }
                    : r,
                ),
              }
            : v,
        ),
      );
    } catch (err) {
      setVariants((prev) =>
        prev.map((v) =>
          v.id === variantId
            ? {
                ...v,
                resizes: v.resizes.map((r) =>
                  r.id === resizeId
                    ? {
                        ...r,
                        loading: false,
                        error:
                          err instanceof Error ? err.message : "Resize failed",
                      }
                    : r,
                ),
              }
            : v,
        ),
      );
    }
  }

  const canGenerate = Boolean(file) && !isLoading;

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black">
      <main className="mx-auto max-w-6xl px-6 py-10">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
          Генератор креативов
        </h1>
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">
          Загрузи исходник, опиши в одном поле что нужно (включая текст) — модель
          сама всё нарисует и разложит.
        </p>

        <div className="mt-8 grid grid-cols-1 gap-8 lg:grid-cols-[360px_1fr]">
          {/* Settings column */}
          <section className="flex flex-col gap-5">
            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Исходное изображение
              </span>
              <input
                type="file"
                accept="image/*"
                onChange={handleFileChange}
                className="rounded-lg border border-zinc-300 bg-white p-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
              />
            </label>

            {previewUrl && (
              <div className="relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-900 dark:border-zinc-800">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={previewUrl}
                  alt="Превью исходника"
                  className="max-h-72 w-full object-contain"
                />
              </div>
            )}

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Промт
              </span>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={7}
                placeholder={
                  "Опиши, что нужно, и впиши сам текст. Например:\n\nПолностью замени текст на этот, размести красиво и читаемо:\nЗаголовок: ...\nПодзаголовок: ...\nЦена (обведи кругом): $149 вместо $3853\nКнопка: ЗАБРОНИРОВАТЬ МЕСТО"
                }
                className="rounded-lg border border-zinc-300 bg-white p-3 text-sm dark:border-zinc-700 dark:bg-zinc-900"
              />
            </label>

            <div className="flex flex-col gap-2">
              <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Формат
              </span>
              <div className="flex flex-wrap gap-2">
                {FORMATS.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setFormatId(f.id)}
                    className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${
                      formatId === f.id
                        ? "border-orange-500 bg-orange-500/10 text-orange-600 dark:text-orange-400"
                        : "border-zinc-300 text-zinc-700 dark:border-zinc-700 dark:text-zinc-300"
                    }`}
                  >
                    {f.label}
                  </button>
                ))}
              </div>
              {selectedFormat?.hint && (
                <span className="text-xs text-zinc-500">
                  {selectedFormat.hint}
                </span>
              )}
            </div>

            <div className="flex flex-col gap-2">
              <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                <input
                  type="checkbox"
                  checked={removeLogos}
                  onChange={(e) => setRemoveLogos(e.target.checked)}
                  className="accent-orange-500"
                />
                Убрать логотипы
              </label>
              <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                <input
                  type="checkbox"
                  checked={removeWatermarks}
                  onChange={(e) => setRemoveWatermarks(e.target.checked)}
                  className="accent-orange-500"
                />
                Убрать водяные знаки
              </label>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Количество
              </span>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => setCount((c) => Math.max(1, c - 1))}
                  className="h-8 w-8 rounded-md border border-zinc-300 text-lg leading-none dark:border-zinc-700"
                >
                  −
                </button>
                <span className="w-6 text-center text-sm">{count}</span>
                <button
                  type="button"
                  onClick={() => setCount((c) => Math.min(MAX_COUNT, c + 1))}
                  className="h-8 w-8 rounded-md border border-zinc-300 text-lg leading-none dark:border-zinc-700"
                >
                  +
                </button>
              </div>
            </div>

            <button
              type="button"
              disabled={!canGenerate}
              onClick={handleGenerate}
              className="rounded-lg bg-orange-500 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? "Генерирую..." : "Generate variants"}
            </button>
            <p className="text-xs text-zinc-500">
              Ожидаемая стоимость: ~${cost} ({count} × ${PRICE_PER_IMAGE})
            </p>

            {error && (
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            )}
          </section>

          {/* Results column */}
          <section className="flex flex-col gap-6">
            <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Варианты {variants.length > 0 && `(${variants.length})`}
            </span>

            {isLoading && (
              <div className="rounded-lg border border-dashed border-zinc-300 p-6 text-sm text-zinc-500 dark:border-zinc-700">
                Генерирую {count} {count === 1 ? "вариант" : "вариантов"}...
              </div>
            )}

            {variants.length === 0 && !isLoading && (
              <div className="flex min-h-64 items-center justify-center rounded-lg border border-dashed border-zinc-300 text-sm text-zinc-500 dark:border-zinc-700">
                Здесь появятся сгенерированные варианты
              </div>
            )}

            <div className="flex flex-col gap-6 overflow-x-auto">
              {variants.map((v) => (
                <VariantCard
                  key={v.id}
                  variant={v}
                  onToggleMenu={toggleMenu}
                  onResize={handleResize}
                />
              ))}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
