import { Config } from "@remotion/cli/config";

// Used by `npm run studio`. Rendering goes through video/scripts/render.mjs (same settings).
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(92);
Config.setConcurrency(4);
const shell = process.env.REMOTION_BROWSER;
if (shell) Config.setBrowserExecutable(shell);
