FROM node:20-slim AS build
WORKDIR /app
COPY package.json ./
RUN npm install
COPY . .
RUN npm run build

# nginx instead of a plain static server: it also reverse-proxies /api to
# the backend container (see nginx.conf) -- the built app has no dev-server
# proxy anymore, so something has to fill that role in production, and this
# also keeps frontend+backend on one public port with no CORS involved.
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
