import type { NextConfig } from "next";

// STATIC_EXPORT=1 builds a static site (frontend/out) that the FastAPI app serves in deployment.
const nextConfig: NextConfig = process.env.STATIC_EXPORT ? { output: "export" } : {};

export default nextConfig;
