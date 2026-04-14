FROM node:20-alpine
RUN apk update && apk upgrade --no-cache
WORKDIR /app
COPY package*.json ./
RUN npm install --production && \
    npm cache clean --force && \
    rm -rf /usr/local/lib/node_modules/npm /usr/local/bin/npm /usr/local/bin/npx
COPY . .
EXPOSE 3014
HEALTHCHECK --interval=30s --timeout=3s CMD wget -qO- http://localhost:3014/health || exit 1
CMD ["node", "src/index.js"]


