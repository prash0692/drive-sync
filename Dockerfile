#below setting threw several security alerts
#FROM python:3.12
#WORKDIR /app
#COPY . .
#RUN pip install -r requirements.txt
#CMD ["python", "-m", "src.sync"]

# Slim base, pinned by digest: small and exactly reproducible this will reduce OS alerts
FROM python:3.12-slim@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b

WORKDIR /app

# Dependencies first, in their own layer, not copying every file in the repo
COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt 

# Only the code the job needs
COPY src/ ./src/
#COPY src/__init__.py src/sync.py ./src/ 
#either add the files you dont need in .dockerignore or copy only the files you need, here, to reduce the attack surface

# Create an unprivileged user and switch to it
RUN useradd --create-home --uid 10001 appuser
USER appuser

CMD ["python", "-m", "src.sync"]