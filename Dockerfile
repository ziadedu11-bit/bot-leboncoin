# Utilise une image Python 3.10 officielle et légère
FROM python:3.10-slim

# Définit le répertoire de travail dans le conteneur
WORKDIR /app

# Copie tout le contenu de ton projet dans le conteneur
COPY . .

# Installe les dépendances Python
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Commande pour lancer ton bot
CMD ["python", "bot.py"]
