# =========================
# Etapa 1: Build da aplicação
# =========================
FROM node:20-alpine AS build

WORKDIR /app

# Copia os arquivos de dependências primeiro para aproveitar cache do Docker
COPY package*.json ./
RUN npm install

# Copia o restante dos arquivos da aplicação
COPY . .

# Define variáveis de ambiente para o build
# Defina as variáveis diretamente aqui ou pode passar essas variáveis no `docker-compose.yml` ou no Render.com.
ENV VITE_URL_AGENT_API=https://macabeu-backend.onrender.com/
ENV VITE_MODE=production

# Roda o build com as variáveis definidas
RUN npm run build

# =========================
# Etapa 2: Servir com Nginx
# =========================
FROM nginx:1.25-alpine

# Copia o build para o Nginx
COPY --from=build /app/dist /usr/share/nginx/html

# Copia o nginx.conf personalizado
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expõe a porta
EXPOSE 80

# Roda o Nginx
CMD ["nginx", "-g", "daemon off;"]
