# syntax=docker/dockerfile:1

FROM node:24-slim@sha256:ba849c60be29959425b8734d57b8b4b7d56f98edd9504c9af091d5281095a71e AS runner

WORKDIR /app
ENV NODE_ENV=production \
    STANDALONE=false \
    HOST=0.0.0.0

ARG TRUEFORGE_VERSION=0.1.4
RUN npm install --omit=dev "@truefoundry/trueforge@${TRUEFORGE_VERSION}" \
  && npm cache clean --force

COPY model-catalog.yaml sandbox-catalog.yaml /app/catalog/

RUN groupadd --gid 10001 trueforge \
  && useradd --uid 10001 --gid trueforge --shell /usr/sbin/nologin trueforge

EXPOSE 8790
USER 10001:10001

CMD ["node", "node_modules/@truefoundry/trueforge/dist/main.js"]
