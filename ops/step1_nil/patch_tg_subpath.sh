#!/usr/bin/env bash
set -euo pipefail

# Step 1 patch: make TG web work behind /tg with minimal code changes.
#
# Usage:
#   WEB_DIR=/opt/tg_digest_system/tg_digest_system/web \
#   bash kb_ring/ops/step1_nil/patch_tg_subpath.sh

WEB_DIR="${WEB_DIR:-/opt/tg_digest_system/tg_digest_system/web}"
WEB_API="${WEB_DIR}/web_api.py"
TEMPLATES_DIR="${WEB_DIR}/templates"

if [[ ! -f "${WEB_API}" ]]; then
  echo "web_api.py not found: ${WEB_API}" >&2
  exit 1
fi
if [[ ! -d "${TEMPLATES_DIR}" ]]; then
  echo "templates dir not found: ${TEMPLATES_DIR}" >&2
  exit 1
fi

TS="$(date +%Y%m%d_%H%M%S)"
cp "${WEB_API}" "${WEB_API}.bak.${TS}"

if ! grep -q "__TG_BASE_PATH_REDIRECT_PATCH__" "${WEB_API}"; then
  cat >> "${WEB_API}" <<'PYCODE'

# __TG_BASE_PATH_REDIRECT_PATCH__
APP_BASE_PATH = os.environ.get("APP_BASE_PATH", "/tg").strip()
if APP_BASE_PATH and not APP_BASE_PATH.startswith("/"):
    APP_BASE_PATH = "/" + APP_BASE_PATH
if APP_BASE_PATH == "/":
    APP_BASE_PATH = ""


def _with_base_path(url: str) -> str:
    if not APP_BASE_PATH or not url.startswith("/"):
        return url
    if url == APP_BASE_PATH or url.startswith(APP_BASE_PATH + "/"):
        return url
    return APP_BASE_PATH + url


@app.middleware("http")
async def apply_base_path_redirects(request: Request, call_next):
    response = await call_next(request)
    location = response.headers.get("location")
    if location and location.startswith("/"):
        response.headers["location"] = _with_base_path(location)
    return response

# __TG_BASE_PATH_REDIRECT_PATCH__ end
PYCODE
fi

for f in "${TEMPLATES_DIR}"/*.html; do
  [[ -f "${f}" ]] || continue
  cp "${f}" "${f}.bak.${TS}"
  if grep -q "__TG_SUBPATH_PATCH__" "${f}"; then
    continue
  fi
  perl -0777 -i -pe 's#<head>#<head>\n    <script>\n    // __TG_SUBPATH_PATCH__\n    (function () {\n        if (window.__TG_SUBPATH_PATCH__) return;\n        window.__TG_SUBPATH_PATCH__ = true;\n        var path = window.location.pathname || \"\";\n        var base = \"\";\n        if (path === \"/tg\" || path.indexOf(\"/tg/\") === 0) base = \"/tg\";\n        window.__tgPrefix = function (u) {\n            if (!u || typeof u !== \"string\") return u;\n            if (!base) return u;\n            if (u === base || u.indexOf(base + \"/\") === 0) return u;\n            if (u.indexOf(\"/\") === 0) return base + u;\n            return u;\n        };\n        var _fetch = window.fetch.bind(window);\n        window.fetch = function (input, init) {\n            if (typeof input === \"string\") return _fetch(window.__tgPrefix(input), init);\n            if (input instanceof Request) {\n                var parsed = new URL(input.url, window.location.origin);\n                if (parsed.origin === window.location.origin) {\n                    return _fetch(window.__tgPrefix(parsed.pathname + parsed.search + parsed.hash), init);\n                }\n            }\n            return _fetch(input, init);\n        };\n        document.addEventListener(\"click\", function (e) {\n            var anchor = e.target && e.target.closest ? e.target.closest(\"a[href]\") : null;\n            if (!anchor) return;\n            var href = anchor.getAttribute(\"href\") || \"\";\n            if (!href || href.indexOf(\"/\") !== 0 || href.indexOf(\"//\") === 0) return;\n            anchor.setAttribute(\"href\", window.__tgPrefix(href));\n        }, true);\n        document.addEventListener(\"submit\", function (e) {\n            var form = e.target;\n            if (!form || !form.getAttribute) return;\n            var action = form.getAttribute(\"action\") || \"\";\n            if (!action || action.indexOf(\"/\") !== 0 || action.indexOf(\"//\") === 0) return;\n            form.setAttribute(\"action\", window.__tgPrefix(action));\n        }, true);\n    })();\n    </script>#' "${f}"

  perl -0777 -i -pe 's/window\.location\.href\s*=\s*("([^"\\]|\\.)*"|'\''([^'\''\\]|\\.)*'\''|`[^`]*`)\s*;/window.location.href = window.__tgPrefix($1);/g' "${f}"
done

echo "TG subpath patch applied."
echo "WEB_DIR=${WEB_DIR}"
echo "Backups: *.bak.${TS}"
