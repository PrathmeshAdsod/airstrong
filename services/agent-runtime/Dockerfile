FROM node:24.13.0-bookworm-slim@sha256:4660b1ca8b28d6d1906fd644abe34b2ed81d15434d26d845ef0aced307cf4b6f

WORKDIR /app

COPY package.json package-lock.json ./
COPY apps/web/package.json ./apps/web/package.json
COPY services/agent-runtime/package.json ./services/agent-runtime/package.json

RUN npm ci --workspace @airstrong/agent-runtime --include-workspace-root

COPY services/agent-runtime ./services/agent-runtime
RUN npm run build --workspace @airstrong/agent-runtime

ENV NODE_ENV=production
EXPOSE 4300

CMD ["npm", "run", "start", "--workspace", "@airstrong/agent-runtime"]
