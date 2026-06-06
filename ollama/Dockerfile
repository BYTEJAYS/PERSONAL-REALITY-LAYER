# Ollama service for PRL — private (no public domain), reached by the API over
# Railway's IPv6 private network at  http://<service>.railway.internal:11434
#
# The model is NOT baked into the image (keeps builds fast / image small).
# The entrypoint pulls it on first boot into a Railway volume mounted at
# /root/.ollama, so subsequent restarts skip the download.
FROM ollama/ollama:latest

# Railway's private network is IPv6-only — bind the unspecified IPv6 address.
# On Linux this is dual-stack, so 127.0.0.1 (the local client below) still works.
ENV OLLAMA_HOST=[::]:11434
# Which model the entrypoint ensures is present (override via Railway var).
ENV OLLAMA_MODEL=llama3.2:3b

# The base image's ENTRYPOINT is `ollama`; replace it with our boot script.
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/bin/bash", "/entrypoint.sh"]
