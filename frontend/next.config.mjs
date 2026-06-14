/** @type {import('next').NextConfig} */

// Guard against shipping a static export that points at localhost. `output: export`
// bakes NEXT_PUBLIC_BACKEND_URL in at build time, so a production build that forgets
// to set it would silently ship a site whose every API call hits localhost. Fail the
// build instead. Pass ALLOW_LOCALHOST_BACKEND=1 to bypass (e.g. testing the export locally).
const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL || "";
const isProdBuild = process.env.NODE_ENV === "production";
const allowLocalhost = process.env.ALLOW_LOCALHOST_BACKEND === "1";
if (
  isProdBuild &&
  !allowLocalhost &&
  (!backendUrl || backendUrl.includes("localhost") || backendUrl.includes("127.0.0.1"))
) {
  throw new Error(
    `[build] NEXT_PUBLIC_BACKEND_URL is "${backendUrl || "unset"}" for a production build. ` +
      "A static export bakes this value in, so the deployed site would call localhost and every " +
      "request would fail. Set NEXT_PUBLIC_BACKEND_URL to the production backend URL before building, " +
      "or pass ALLOW_LOCALHOST_BACKEND=1 to override for local export testing."
  );
}

const nextConfig = {
  output: "export",
  trailingSlash: true,
};

export default nextConfig;
