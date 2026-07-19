"use client";

import { useState } from "react";

const ASPECT_RATIOS = ["1:1", "3:4", "4:3", "9:16", "16:9"] as const;
type AspectRatio = (typeof ASPECT_RATIOS)[number];

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [prompt, setPrompt] = useState("");
  const [aspectRatio, setAspectRatio] = useState<AspectRatio>("1:1");
  const [resultUrl, setResultUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const selected = e.target.files?.[0] ?? null;
    setFile(selected);
    setResultUrl(null);
    setError(null);
    setPreviewUrl(selected ? URL.createObjectURL(selected) : null);
  }

  async function handleGenerate() {
    if (!file || !prompt.trim()) return;

    setIsLoading(true);
    setError(null);
    setResultUrl(null);

    try {
      const formData = new FormData();
      formData.append("image", file);
      formData.append("prompt", prompt);
      formData.append("aspectRatio", aspectRatio);

      const res = await fetch("/api/generate", {
        method: "POST",
        body: formData,
      });

      const data = await res.json();

      if (!res.ok) {
        throw new Error(data.error ?? "Generation failed");
      }

      setResultUrl(data.image);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Generation failed");
    } finally {
      setIsLoading(false);
    }
  }

  const canGenerate = Boolean(file) && prompt.trim().length > 0 && !isLoading;

  return (
    <div className="min-h-screen bg-zinc-50 dark:bg-black">
      <main className="mx-auto max-w-5xl px-6 py-12">
        <h1 className="text-2xl font-semibold text-black dark:text-zinc-50">
          Генератор изображений
        </h1>
        <p className="mt-2 text-zinc-600 dark:text-zinc-400">
          Загрузи картинку, опиши что изменить, выбери формат — модель
          сгенерирует новый вариант.
        </p>

        <div className="mt-8 grid grid-cols-1 gap-8 md:grid-cols-2">
          <section className="flex flex-col gap-4">
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
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={previewUrl}
                alt="Превью исходного изображения"
                className="max-h-80 w-full rounded-lg border border-zinc-200 object-contain dark:border-zinc-800"
              />
            )}

            <label className="flex flex-col gap-2">
              <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Что изменить
              </span>
              <textarea
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                rows={4}
                placeholder="Например: замени фон на закат, убери текст с плаката"
                className="rounded-lg border border-zinc-300 bg-white p-3 text-sm dark:border-zinc-700 dark:bg-zinc-900"
              />
            </label>

            <div className="flex flex-col gap-2">
              <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
                Формат
              </span>
              <div className="flex flex-wrap gap-2">
                {ASPECT_RATIOS.map((ratio) => (
                  <button
                    key={ratio}
                    type="button"
                    onClick={() => setAspectRatio(ratio)}
                    className={`rounded-lg border px-3 py-1.5 text-sm transition-colors ${
                      aspectRatio === ratio
                        ? "border-orange-500 bg-orange-500/10 text-orange-600 dark:text-orange-400"
                        : "border-zinc-300 text-zinc-700 dark:border-zinc-700 dark:text-zinc-300"
                    }`}
                  >
                    {ratio}
                  </button>
                ))}
              </div>
            </div>

            <button
              type="button"
              disabled={!canGenerate}
              onClick={handleGenerate}
              className="mt-2 rounded-lg bg-orange-500 px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-orange-600 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {isLoading ? "Генерирую..." : "Generate"}
            </button>

            {error && (
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            )}
          </section>

          <section className="flex flex-col gap-2">
            <span className="text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Результат
            </span>
            <div className="flex min-h-80 items-center justify-center rounded-lg border border-dashed border-zinc-300 bg-white dark:border-zinc-700 dark:bg-zinc-900">
              {isLoading && (
                <span className="text-sm text-zinc-500">Генерирую...</span>
              )}
              {!isLoading && resultUrl && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={resultUrl}
                  alt="Сгенерированное изображение"
                  className="max-h-[32rem] w-full rounded-lg object-contain"
                />
              )}
              {!isLoading && !resultUrl && (
                <span className="text-sm text-zinc-500">
                  Здесь появится результат
                </span>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
}
