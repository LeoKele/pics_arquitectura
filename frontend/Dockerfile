FROM nginx:alpine

# 1. Copiamos TODO el contenido actual (html, css, js) a Nginx
COPY . /usr/share/nginx/html/

# Exponemos el puerto
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
