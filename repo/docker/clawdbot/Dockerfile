FROM node:22-bullseye

WORKDIR /app

RUN npm install -g clawdbot

ENV XDG_CONFIG_HOME=/sandbox/clawdbot
ENV CLAWDBOT_GATEWAY_BIND=loopback
ENV CLAWDBOT_GATEWAY_AUTH_MODE=token

# Run gateway in the foreground (container-friendly; no systemd)
CMD ["clawdbot", "gateway", "run"]
