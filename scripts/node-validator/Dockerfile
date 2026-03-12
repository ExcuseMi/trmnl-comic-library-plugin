FROM node:24-alpine

WORKDIR /app

COPY package.json ./
RUN npm install --production

COPY validate-feeds.js ./
COPY transform.js ./

ENTRYPOINT ["node", "validate-feeds.js"]
