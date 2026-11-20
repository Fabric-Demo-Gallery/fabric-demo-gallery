FROM mcr.microsoft.com/devcontainers/javascript-node:1-22-bookworm AS build

WORKDIR /app
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

COPY package.json pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY index.html vite.config.ts tsconfig*.json ./
COPY public ./public
COPY src ./src
RUN pnpm build

FROM mcr.microsoft.com/devcontainers/javascript-node:1-22-bookworm

ENV NODE_ENV=production
ENV PORT=8080

WORKDIR /app
RUN corepack enable && corepack prepare pnpm@9.15.9 --activate

COPY package.json pnpm-lock.yaml server.js ./
RUN pnpm install --prod --frozen-lockfile
COPY --from=build /app/dist ./dist

EXPOSE 8080
CMD ["node", "server.js"]

