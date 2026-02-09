# NaviSound Gateway — Node.js Express WebSocket relay
FROM node:20-alpine

WORKDIR /app

COPY gateway/package.json ./
RUN npm install --production

COPY gateway/ ./

ENV EXPRESS_PORT=3000
ENV FASTAPI_WS_URL=ws://backend:8000/agent/stream

EXPOSE 3000

CMD ["node", "server.js"]
