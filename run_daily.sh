#!/bin/bash
set -euo pipefail

REPO="/Users/axelhernandez/Projects/daily-study-news-companion"
cd "$REPO"

# Asegura carpetas de salida/logs
mkdir -p "$REPO/docs/charts" "$REPO/logs"

# Ejecuta con el Python del venv (Python leerá .env vía load_dotenv)
"$REPO/.venv/bin/python" src/main.py >> "$REPO/logs/launchd.run.log" 2>&1

# --- Autopublish a GitHub Pages (no romper si falla) ---
if ! git diff --quiet -- docs; then
  set +e
  git add docs
  git commit -m "chore: update daily report $(date +'%Y-%m-%d %H:%M')"
  git push origin main
  publish_rc=$?
  set -e
  if [ $publish_rc -ne 0 ]; then
    echo "[publish] git push failed (sin credenciales o fuera de línea), continuando" >> "$REPO/logs/launchd.run.log"
  else
    echo "[publish] git push ok" >> "$REPO/logs/launchd.run.log"
  fi
fi

