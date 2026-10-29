#!/bin/sh
# Container entrypoint: unpack the patient data from a secret env var (it is never in git), then serve.
set -e
if [ ! -d data/patient-0000-0001 ] && [ -n "$DATA_ZIP_B64" ]; then
  echo "$DATA_ZIP_B64" | base64 -d > /tmp/data.zip
  python3 -c "import zipfile; zipfile.ZipFile('/tmp/data.zip').extractall('.')"
  rm /tmp/data.zip
fi
exec uvicorn --app-dir backend app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
