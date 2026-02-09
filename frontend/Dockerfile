# NaviSound Frontend — React + Vite production build
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json ./
RUN npm install

COPY . .
RUN npm run build

# Serve with lightweight nginx + WebSocket proxy to gateway
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html

# Nginx config: SPA fallback + /ws proxy → gateway container
RUN cat > /etc/nginx/conf.d/default.conf << 'NGINX'
upstream gateway {
    server gateway:3000;
}

server {
    listen 80;
    root /usr/share/nginx/html;
    index index.html;

    # SPA fallback
    location / {
        try_files $uri $uri/ /index.html;
    }

    # WebSocket proxy to gateway
    location /ws {
        proxy_pass http://gateway;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # Health check
    location /health {
        return 200 'ok';
        add_header Content-Type text/plain;
    }
}
NGINX

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
