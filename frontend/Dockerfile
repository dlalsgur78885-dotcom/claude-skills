# ─── build stage ──────────────────────────────────────────
FROM node:22-alpine AS builder
WORKDIR /app

# Install deps first (caching)
COPY package.json package-lock.json* ./
RUN npm ci

# NEXT_PUBLIC_API_URL is baked into the bundle at build time.
# Default points at same-origin /api (works behind nginx reverse-proxy on prod).
ARG NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

COPY . .
RUN npm run build

# ─── runtime stage ────────────────────────────────────────
FROM node:22-alpine AS runner
WORKDIR /app

ENV NODE_ENV=production
ENV PORT=3000
ENV HOSTNAME=0.0.0.0

# Standalone output: copy the minimal server bundle + static + public
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
CMD ["node", "server.js"]
