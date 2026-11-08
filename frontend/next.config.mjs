/** @type {import('next').NextConfig} */
const isProd = process.env.NODE_ENV === "production";

// Content Security Policy compatible with Next.js App Router (Finding 6)
const cspDirectives = [
  "default-src 'self'",
  `script-src 'self' 'unsafe-inline' ${isProd ? "" : "'unsafe-eval'"}`,
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' blob: data: https://*.amazonaws.com",
  "font-src 'self' data:",
  "connect-src 'self' http://localhost:* ws://localhost:* http://127.0.0.1:* https:",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "base-uri 'self'",
  "object-src 'none'",
]
  .join("; ")
  .trim();

const nextConfig = {
  output: "standalone",
  reactStrictMode: true,
  poweredByHeader: false,
  compress: true,
  images: {
    remotePatterns: [
      {
        protocol: "https",
        hostname: "**.amazonaws.com",
      },
    ],
  },
  experimental: {
    typedRoutes: true,
  },
  async headers() {
    const securityHeaders = [
      { key: "Content-Security-Policy", value: cspDirectives },
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
      {
        key: "Permissions-Policy",
        value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), vr=()",
      },
      { key: "X-XSS-Protection", value: "0" },
    ];

    if (isProd) {
      securityHeaders.push({
        key: "Strict-Transport-Security",
        value: "max-age=31536000; includeSubDomains; preload",
      });
    }

    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};

export default nextConfig;
