#!/usr/bin/env bash
set -euo pipefail

# Step 1 patch: make transcription frontend work behind /transcription.
#
# Usage:
#   TRANSCRIPTION_DIR=/opt/transcription \
#   bash kb_ring/ops/step1_nil/patch_transcription_subpath.sh

TRANSCRIPTION_DIR="${TRANSCRIPTION_DIR:-/opt/transcription}"
INDEX_HTML="${TRANSCRIPTION_DIR}/static/index.html"

if [[ ! -f "${INDEX_HTML}" ]]; then
  echo "index.html not found: ${INDEX_HTML}" >&2
  exit 1
fi

TS="$(date +%Y%m%d_%H%M%S)"
cp "${INDEX_HTML}" "${INDEX_HTML}.bak.${TS}"

if ! grep -q "__TRANSCRIPTION_SUBPATH_PATCH__" "${INDEX_HTML}"; then
  perl -0777 -i -pe 's#<script>#<script>\n        \/\/ __TRANSCRIPTION_SUBPATH_PATCH__\n        (function () {\n            if (window.__TRANSCRIPTION_SUBPATH_PATCH__) return;\n            window.__TRANSCRIPTION_SUBPATH_PATCH__ = true;\n            var path = window.location.pathname || \"\";\n            var base = \"\";\n            if (path === \"/transcription\" || path.indexOf(\"/transcription/\") === 0) base = \"/transcription\";\n            window.__transcriptionPrefix = function (u) {\n                if (!u || typeof u !== \"string\") return u;\n                if (!base) return u;\n                if (u === base || u.indexOf(base + \"/\") === 0) return u;\n                if (u.indexOf(\"/\") === 0) return base + u;\n                return u;\n            };\n            var _fetch = window.fetch.bind(window);\n            window.fetch = function (input, init) {\n                if (typeof input === \"string\") return _fetch(window.__transcriptionPrefix(input), init);\n                if (input instanceof Request) {\n                    var parsed = new URL(input.url, window.location.origin);\n                    if (parsed.origin === window.location.origin) {\n                        return _fetch(window.__transcriptionPrefix(parsed.pathname + parsed.search + parsed.hash), init);\n                    }\n                }\n                return _fetch(input, init);\n            };\n        })();\n        </script>\n\n        <script>#' "${INDEX_HTML}"
fi

echo "Transcription subpath patch applied."
echo "INDEX_HTML=${INDEX_HTML}"
echo "Backup: ${INDEX_HTML}.bak.${TS}"
