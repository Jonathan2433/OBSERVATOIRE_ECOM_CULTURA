# Front Direction B — statique pur (aucun build node). nginx sert les fichiers
# et proxifie /api vers l'API (cf. nginx.conf). Contexte de build : app/web-b/.
FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY index.html /usr/share/nginx/html/index.html
COPY api.js /usr/share/nginx/html/api.js
COPY app.js /usr/share/nginx/html/app.js
COPY assets /usr/share/nginx/html/assets
EXPOSE 80
