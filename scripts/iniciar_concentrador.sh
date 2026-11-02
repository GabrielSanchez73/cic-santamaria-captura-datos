#!/usr/bin/env bash
# Arranca el concentrador escuchando en toda la red local (para que el ESP32 pueda llegar a el).
# Uso: ./scripts/iniciar_concentrador.sh [puerto]
set -euo pipefail
cd "$(dirname "$0")/.."
PUERTO="${1:-8000}"
if [ -d ".venv" ]; then source .venv/bin/activate; fi
IP=$(hostname -I 2>/dev/null | awk '{print $1}')
echo "Concentrador en http://${IP:-<tu-IP>}:${PUERTO}  (jornada: /jornada, documentacion: /docs)"
exec python -m uvicorn app.main:app --host 0.0.0.0 --port "$PUERTO"
