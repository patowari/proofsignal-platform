import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Next 16 blocks dev-server resources requested from a host other than the
  // one in the address bar, and treats 127.0.0.1 and localhost as different
  // origins. Without this, opening the app at 127.0.0.1 returns 403 for every
  // JS chunk, so React never hydrates and nothing on the page responds --
  // which looks like broken UI rather than a config issue.
  // Development only; it has no effect on a production build.
  allowedDevOrigins: ["127.0.0.1", "localhost"],
};

export default nextConfig;
