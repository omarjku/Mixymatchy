#!/bin/sh
# Container entrypoint: unpack the patient data from a secret env var (it is never in git), then serve.
set -e
TARGET=data/patient-0000-0001
if [ ! -d "$TARGET/documents" ]; then
  if [ -z "$DATA_ZIP_B64" ]; then
    echo "start.sh: DATA_ZIP_B64 is not set and $TARGET is missing; add the variable in the host's settings." >&2
    exit 1
  fi
  echo "start.sh: DATA_ZIP_B64 has ${#DATA_ZIP_B64} characters; unpacking"
  printf '%s' "$DATA_ZIP_B64" | tr -d ' \r\n' | base64 -d > /tmp/data.zip
  rm -rf /tmp/unpack && mkdir -p /tmp/unpack
  python3 -c "import zipfile,sys; zipfile.ZipFile('/tmp/data.zip').extractall('/tmp/unpack')"
  # Accept any zip layout: find the folder that holds documents/ for this patient.
  SRC=$(find /tmp/unpack -type d -name documents -path '*patient-0000-0001/documents' | head -n 1)
  if [ -z "$SRC" ]; then
    echo "start.sh: no patient-0000-0001/documents folder inside the zip. Zip contents:" >&2
    find /tmp/unpack -maxdepth 3 >&2
    exit 1
  fi
  mkdir -p data && rm -rf "$TARGET" && cp -R "$(dirname "$SRC")" "$TARGET"
  rm -rf /tmp/unpack /tmp/data.zip
  echo "start.sh: unpacked $(ls "$TARGET/documents" | wc -l) documents"
fi
exec uvicorn --app-dir backend app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
