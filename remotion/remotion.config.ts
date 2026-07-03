/**
 * Note: When using the Node.JS APIs, the config file
 * doesn't apply. Instead, pass options directly to the APIs.
 *
 * All configuration options: https://remotion.dev/docs/config
 */

import { Config } from "@remotion/cli/config";
import { enableTailwind } from '@remotion/tailwind-v4';
import path from "node:path";

Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);

Config.overrideWebpackConfig((config) => {
  const tailwindEnabled = enableTailwind(config);
  return {
    ...tailwindEnabled,
    resolve: {
      ...tailwindEnabled.resolve,
      alias: {
        ...(tailwindEnabled.resolve?.alias || {}),
        "@": path.resolve(__dirname, "src"),
      },
    },
  };
});
