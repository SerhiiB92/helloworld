import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Ensure the bundled fonts used by the text-compositing route are traced
  // into the serverless function on Vercel.
  outputFileTracingIncludes: {
    "/api/compose": ["./public/fonts/**/*"],
  },
  // Native module: keep it external so its prebuilt binaries load correctly.
  serverExternalPackages: ["@napi-rs/canvas"],
};

export default nextConfig;
