# ==============================================================================
# Multi-Stage Production & Development Dockerfile for Next.js 14 Frontend
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Base Alpine Image
# ------------------------------------------------------------------------------
FROM node:20-alpine AS base

RUN apk add --no-cache libc6-compat wget
WORKDIR /app

# ------------------------------------------------------------------------------
# Stage 2: Install Dependencies (All dependencies for build and development)
# ------------------------------------------------------------------------------
FROM base AS deps

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci

# ------------------------------------------------------------------------------
# Stage 3: Development Image (Targeted in docker-compose.dev.yml)
# ------------------------------------------------------------------------------
FROM base AS dev

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NODE_ENV=development
ENV NEXT_TELEMETRY_DISABLED=1

EXPOSE 3000

CMD ["npm", "run", "dev"]

# ------------------------------------------------------------------------------
# Stage 4: Production Application Builder
# ------------------------------------------------------------------------------
FROM base AS builder

WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .

ENV NEXT_TELEMETRY_DISABLED=1
ENV NODE_ENV=production

RUN npm run build

# ------------------------------------------------------------------------------
# Stage 5: Production Runner (Minimal standalone, non-root nextjs user)
# ------------------------------------------------------------------------------
FROM node:20-alpine AS runner

WORKDIR /app

ENV NODE_ENV=production
ENV NEXT_TELEMETRY_DISABLED=1
ENV PORT=3000
ENV HOSTNAME="0.0.0.0"

RUN apk add --no-cache wget && \
    addgroup --system --gid 1001 nodejs && \
    adduser --system --uid 1001 nextjs

COPY --from=builder /app/public ./public
COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static

USER nextjs

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:3000/api/health || exit 1

CMD ["node", "server.js"]
