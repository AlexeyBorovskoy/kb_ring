#!/usr/bin/env bash
set -euo pipefail

# KB-RING AI worker preflight (run on your laptop / Linux VM).
#
# Purpose:
# - Validate that the machine can act as a remote AI worker (embeddings/rerank).
# - Collect CPU/RAM/disk/network/python info.
# - Optionally run model load + tiny inference tests (downloads can be multiple GB).
#
# Usage:
#   bash scripts/ai_worker_preflight.sh
#
# Optional (recommended once):
#   RUN_MODEL_TESTS=1 bash scripts/ai_worker_preflight.sh
#
# Optional settings:
#   EMBED_MODEL=sentence-transformers/multilingual-e5-base
#   RERANK_MODEL=BAAI/bge-reranker-base
#   HF_HOME=$HOME/.cache/huggingface
#   NIL_BASE_URL=https://kb.<ip>.nip.io   # optional connectivity check

TS="$(date +%Y%m%d_%H%M%S)"
REPORT="/tmp/kb_ring_ai_worker_preflight_${TS}.txt"

EMBED_MODEL="${EMBED_MODEL:-sentence-transformers/multilingual-e5-base}"
RERANK_MODEL="${RERANK_MODEL:-BAAI/bge-reranker-base}"
RUN_MODEL_TESTS="${RUN_MODEL_TESTS:-0}"
NIL_BASE_URL="${NIL_BASE_URL:-}"

say() { echo "$*" | tee -a "${REPORT}"; }
have() { command -v "$1" >/dev/null 2>&1; }

section() { say ""; say "== $* =="; }
kv() { local k="$1"; shift; say "${k}: $*"; }

fail_count=0
warn_count=0
fail() { say "FAIL: $*"; fail_count=$((fail_count+1)); }
warn() { say "WARN: $*"; warn_count=$((warn_count+1)); }
ok() { say "OK:   $*"; }

say "KB-RING AI Worker Preflight"
kv "Timestamp" "${TS}"
kv "Report" "${REPORT}"

section "OS"
if [[ -f /etc/os-release ]]; then
  # shellcheck disable=SC1091
  . /etc/os-release
  kv "OS" "${PRETTY_NAME:-unknown}"
else
  kv "OS" "unknown (no /etc/os-release)"
fi
kv "Kernel" "$(uname -r)"

section "CPU"
if have nproc; then kv "nproc" "$(nproc)"; fi
if have lscpu; then
  lscpu | egrep -i 'Model name|CPU\\(s\\)|Thread\\(s\\) per core|Core\\(s\\) per socket|Socket\\(s\\)' | sed 's/^/  /' | tee -a "${REPORT}"
else
  warn "lscpu not found"
fi

section "Memory"
if have free; then free -h | tee -a "${REPORT}"; else warn "free not found"; fi

section "Disk"
df -h . | tee -a "${REPORT}"
kv "HF cache dir" "${HF_HOME:-$HOME/.cache/huggingface}"

section "Network"
if have curl; then
  curl -fsS -m 5 https://pypi.org >/dev/null 2>&1 && ok "pypi.org reachable" || warn "pypi.org not reachable (pip installs may fail)"
  curl -fsS -m 8 https://huggingface.co >/dev/null 2>&1 && ok "huggingface.co reachable" || warn "huggingface.co not reachable (model downloads may fail)"
  if [[ -n "${NIL_BASE_URL}" ]]; then
    curl -fsS -m 8 "${NIL_BASE_URL%/}/kb/health" >/dev/null 2>&1 && ok "Nil KB health reachable" || warn "Nil KB health NOT reachable"
  fi
else
  warn "curl not found"
fi

section "Python"
if have python3; then kv "python3" "$(python3 --version 2>&1)"; else fail "python3 not found"; fi
if have pip3; then kv "pip3" "$(pip3 --version 2>&1)"; else warn "pip3 not found"; fi

section "GPU (optional)"
if have nvidia-smi; then nvidia-smi | sed -n '1,20p' | tee -a "${REPORT}"; else kv "nvidia-smi" "not found (CPU mode)"; fi

section "Python Imports (no installs)"
python3 - <<'PY' 2>&1 | tee -a "${REPORT}" || true
import sys
mods = ["torch", "sentence_transformers", "transformers"]
print("python:", sys.version.split()[0])
for m in mods:
    try:
        __import__(m)
        print("import", m, "OK")
    except Exception as e:
        print("import", m, "FAIL:", str(e))
PY

if [[ "${RUN_MODEL_TESTS}" == "1" ]]; then
  section "Model Tests (will download if missing)"
  kv "EMBED_MODEL" "${EMBED_MODEL}"
  kv "RERANK_MODEL" "${RERANK_MODEL}"
  say "Note: first run may download multiple GB."
  python3 - <<PY 2>&1 | tee -a "${REPORT}"
import os, time
from sentence_transformers import SentenceTransformer

embed_model = os.environ.get("EMBED_MODEL", "${EMBED_MODEL}")
rerank_model = os.environ.get("RERANK_MODEL", "${RERANK_MODEL}")

t0 = time.time()
print("Loading embed model:", embed_model)
m = SentenceTransformer(embed_model, device="cpu")
v = m.encode(["KB-RING smoke test"], normalize_embeddings=True)
print("Embed dims:", len(v[0]))
print("Embed ok, dt=%.2fs" % (time.time() - t0))

print("Loading rerank model:", rerank_model)
t1 = time.time()
_ = SentenceTransformer(rerank_model, device="cpu")
print("Rerank model loaded (load-smoke), dt=%.2fs" % (time.time() - t1))
PY
else
  section "Model Tests"
  say "Skipped (set RUN_MODEL_TESTS=1 to run)."
fi

section "Result"
kv "WARN" "${warn_count}"
kv "FAIL" "${fail_count}"
if (( fail_count > 0 )); then
  say "Overall: FAIL (see ${REPORT})"
  exit 1
fi
say "Overall: OK (see ${REPORT})"

