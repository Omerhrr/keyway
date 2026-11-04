#!/bin/bash
# Bring up the whole Keyway stack (idempotent): FastAPI :8000, LLM service :8001, Nuxt :3000.
ZDIR="/home/z/my-project/.zscripts"
D="/home/z/my-project/scripts/daemon.sh"

kill_port() {  # kill whatever listens on a port (stale dev servers etc.)
  local port="$1"
  local pids
  pids=$(fuser -n tcp "$port" 2>/dev/null | tr -s ' ')
  if [ -n "$pids" ]; then
    echo "[up] freeing port $port (pids:$pids)"
    kill $pids 2>/dev/null
    sleep 1
    kill -9 $pids 2>/dev/null
  fi
}

bash "$D" keyway-api /home/z/my-project/backend /home/z/my-project/backend/start.sh
bash "$D" llm-service /home/z/my-project/mini-services/llm-service bun run dev
kill_port 3000
bash "$D" nuxt /home/z/my-project bun run dev

# wait for health
for i in $(seq 1 45); do
  if curl -s --max-time 2 http://localhost:8000/api/health >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -s --max-time 2 http://localhost:8000/api/health >/dev/null 2>&1 && echo "[up] API healthy" || echo "[up] API NOT ready (check .zscripts/daemon-keyway-api.log)"
curl -s --max-time 2 http://localhost:8001/health >/dev/null 2>&1 && echo "[up] LLM service healthy" || echo "[up] LLM service not ready (rules-only fallback active)"
for i in $(seq 1 60); do
  if curl -s --max-time 2 -o /dev/null http://localhost:3000/ ; then echo "[up] Nuxt up on 3000"; break; fi
  sleep 1
done
