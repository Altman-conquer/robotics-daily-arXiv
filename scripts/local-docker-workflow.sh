#!/usr/bin/env bash
set -Eeuo pipefail

log() {
  printf '\n[%s] %s\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')" "$*"
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    fail "Missing required environment variable: ${name}"
  fi
}

derive_repo_info() {
  if [ -z "${REPO_OWNER:-}" ] || [ -z "${REPO_NAME:-}" ]; then
    if [[ "${ORIGINAL_REMOTE_URL:-}" =~ github.com[:/]([^/]+)/([^/.]+)(\.git)?$ ]]; then
      export REPO_OWNER="${REPO_OWNER:-${BASH_REMATCH[1]}}"
      export REPO_NAME="${REPO_NAME:-${BASH_REMATCH[2]}}"
    fi
  fi

  require_env REPO_OWNER
  require_env REPO_NAME
}

push_remote() {
  if [ -n "${GIT_PUSH_URL:-}" ]; then
    printf '%s' "$GIT_PUSH_URL"
  elif [ -n "${GIT_PUSH_TOKEN:-}" ]; then
    printf 'https://x-access-token:%s@github.com/%s/%s.git' "$GIT_PUSH_TOKEN" "$REPO_OWNER" "$REPO_NAME"
  else
    printf 'origin'
  fi
}

configure_ssh_key() {
  local source_key="${SSH_PRIVATE_KEY_FILE:-}"
  local source_pub="${SSH_PUBLIC_KEY_FILE:-}"

  if [ -z "$source_key" ] && [ -f /run/host-ssh/id_ed25519 ]; then
    source_key="/run/host-ssh/id_ed25519"
  fi
  if [ -z "$source_pub" ] && [ -f /run/host-ssh/id_ed25519.pub ]; then
    source_pub="/run/host-ssh/id_ed25519.pub"
  fi

  if [ -z "$source_key" ]; then
    return
  fi
  if [ ! -f "$source_key" ]; then
    fail "SSH private key file not found: ${source_key}"
  fi

  mkdir -p /root/.ssh /tmp/docker-ssh
  chmod 700 /root/.ssh /tmp/docker-ssh
  cp "$source_key" /tmp/docker-ssh/id_ed25519
  chmod 600 /tmp/docker-ssh/id_ed25519

  if [ -n "$source_pub" ] && [ -f "$source_pub" ]; then
    cp "$source_pub" /tmp/docker-ssh/id_ed25519.pub
    chmod 644 /tmp/docker-ssh/id_ed25519.pub
  fi

  export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -i /tmp/docker-ssh/id_ed25519 -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new}"
  log "SSH key configured for git operations"
}

git_push_with_retry() {
  local branch="$1"
  local remote
  remote="$(push_remote)"

  for attempt in 1 2 3; do
    log "Pushing ${branch}, attempt ${attempt}"
    if git push "$remote" "$branch"; then
      return 0
    fi

    log "Push failed; pulling latest ${branch} before retry"
    git pull --rebase "$remote" "$branch" || true
  done

  fail "Failed to push ${branch} after 3 attempts"
}

ensure_clean_worktree() {
  if [ "${ALLOW_DIRTY_WORKTREE:-false}" = "true" ]; then
    log "ALLOW_DIRTY_WORKTREE=true; skipping clean worktree guard"
    return
  fi

  if [ -n "$(git status --porcelain)" ]; then
    git status --short >&2
    fail "Worktree is not clean. Commit/stash local changes or set ALLOW_DIRTY_WORKTREE=true."
  fi
}

cleanup() {
  if [ -n "${RUN_DIR:-}" ] && [ "${KEEP_RUN_DIR:-false}" != "true" ]; then
    rm -rf "$RUN_DIR"
  elif [ -n "${RUN_DIR:-}" ]; then
    log "Keeping run directory: ${RUN_DIR}"
  fi
}

main() {
  require_env OPENAI_API_KEY

  git config --global --add safe.directory /app >/dev/null 2>&1 || true
  git config --global --add safe.directory /app/.git >/dev/null 2>&1 || true

  export LANGUAGE="${LANGUAGE:-Chinese}"
  export CATEGORIES="${CATEGORIES:-cs.CV,cs.CL}"
  export MODEL_NAME="${MODEL_NAME:-gpt-4o-mini}"
  export OPENAI_BASE_URL="${OPENAI_BASE_URL:-https://api.openai.com/v1}"
  export AI_MAX_WORKERS="${AI_MAX_WORKERS:-1}"
  export PUSH_CHANGES="${PUSH_CHANGES:-true}"
  export TOKEN_GITHUB="${TOKEN_GITHUB:-${GIT_PUSH_TOKEN:-}}"
  export EMAIL="${EMAIL:-${GIT_USER_EMAIL:-}}"
  export NAME="${NAME:-${GIT_USER_NAME:-}}"

  require_env EMAIL
  require_env NAME
  configure_ssh_key

  if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    fail "/app must be a git repository. Run with the repository mounted at /app."
  fi

  ORIGINAL_BRANCH="$(git branch --show-current)"
  if [ -z "$ORIGINAL_BRANCH" ]; then
    fail "Repository is in detached HEAD state; checkout main before running."
  fi
  ORIGINAL_REMOTE_URL="$(git remote get-url origin 2>/dev/null || true)"
  if [ -z "$ORIGINAL_REMOTE_URL" ]; then
    fail "Repository has no origin remote"
  fi
  trap cleanup EXIT

  derive_repo_info
  ensure_clean_worktree

  RUN_DIR="$(mktemp -d)"
  log "Cloning clean source branch into ${RUN_DIR}"
  git clone --branch "$ORIGINAL_BRANCH" /app "$RUN_DIR"
  cd "$RUN_DIR"
  git remote set-url origin "$ORIGINAL_REMOTE_URL"

  log "Configuration"
  echo "  date: ${RUN_DATE:-auto UTC date}"
  echo "  repo: ${REPO_OWNER}/${REPO_NAME}"
  echo "  branch: ${ORIGINAL_BRANCH}"
  echo "  run dir: ${RUN_DIR}"
  echo "  language: ${LANGUAGE}"
  echo "  categories: ${CATEGORIES}"
  echo "  model: ${MODEL_NAME}"
  echo "  ai workers: ${AI_MAX_WORKERS}"
  echo "  push changes: ${PUSH_CHANGES}"

  log "Installing Python dependencies"
  if [ "${SKIP_UV_SYNC:-false}" != "true" ]; then
    uv sync --frozen || uv sync
  fi
  # shellcheck disable=SC1091
  source .venv/bin/activate

  local today
  today="${RUN_DATE:-$(date -u '+%Y-%m-%d')}"
  mkdir -p data assets
  rm -f "data/${today}.jsonl" "data/${today}_AI_enhanced_${LANGUAGE}.jsonl" "data/${today}.md"

  log "Crawling arXiv papers for ${today}"
  (
    cd daily_arxiv
    scrapy crawl arxiv -o "../data/${today}.jsonl"
  )

  if [ ! -s "data/${today}.jsonl" ]; then
    fail "Crawling finished but data/${today}.jsonl was not generated"
  fi

  log "Checking duplicates"
  local dedup_exit_code
  set +e
  (
    cd daily_arxiv
    python daily_arxiv/check_stats.py
  )
  dedup_exit_code=$?
  set -e

  case "$dedup_exit_code" in
    0)
      log "New content found; continuing"
      ;;
    1)
      log "No new content after deduplication; stopping without error"
      exit 0
      ;;
    2)
      fail "Deduplication processing error"
      ;;
    *)
      fail "Unknown deduplication exit code: ${dedup_exit_code}"
      ;;
  esac

  log "Running AI enhancement"
  (
    cd ai
    python enhance.py --data "../data/${today}.jsonl" --max_workers "$AI_MAX_WORKERS"
  )

  local ai_file="data/${today}_AI_enhanced_${LANGUAGE}.jsonl"
  if [ ! -s "$ai_file" ]; then
    fail "AI enhancement did not generate ${ai_file}"
  fi

  log "Converting to Markdown"
  (
    cd to_md
    python convert.py --data "../${ai_file}"
  )

  log "Updating file list"
  ls data/*.jsonl | sed 's|data/||' > assets/file-list.txt

  log "Injecting auth config"
  local password_hash
  if [ -z "${ACCESS_PASSWORD:-}" ]; then
    password_hash="DISABLED_NO_PASSWORD_SET_IN_SECRETS"
  else
    password_hash="$(echo -n "$ACCESS_PASSWORD" | openssl dgst -sha256 -hex | awk '{print $2}')"
  fi
  sed -i "s/passwordHash: '.*'/passwordHash: '${password_hash}'/" js/auth-config.js

  log "Injecting repository data config"
  sed -i "s/repoOwner: '.*'/repoOwner: '${REPO_OWNER}'/" js/data-config.js
  sed -i "s/repoName: '.*'/repoName: '${REPO_NAME}'/" js/data-config.js

  if [ "$PUSH_CHANGES" != "true" ]; then
    log "PUSH_CHANGES=false; skipping commits and pushes"
    return
  fi

  log "Committing generated config changes on ${ORIGINAL_BRANCH}"
  git config user.email "$EMAIL"
  git config user.name "$NAME"
  git add js/auth-config.js js/data-config.js
  if git diff --staged --quiet; then
    log "No main branch config changes to commit"
  else
    git commit -m "chore: update local deployment config"
  fi

  git_push_with_retry "$ORIGINAL_BRANCH"

  log "Preparing data files for data branch"
  local temp_dir
  temp_dir="$(mktemp -d)"
  mkdir -p "${temp_dir}/data" "${temp_dir}/assets"
  cp -r data/* "${temp_dir}/data/" 2>/dev/null || true
  cp assets/file-list.txt "${temp_dir}/assets/" 2>/dev/null || true
  rm -f data/*.jsonl data/*.md assets/file-list.txt 2>/dev/null || true

  log "Checking out data branch"
  local remote
  remote="$(push_remote)"
  if git ls-remote --heads "$remote" data | grep -q data; then
    git fetch "$remote" data
    if git show-ref --verify --quiet refs/heads/data; then
      git checkout data
      git reset --hard FETCH_HEAD
    else
      git checkout -b data FETCH_HEAD
    fi
  else
    git checkout --orphan data
    git rm -rf --cached . 2>/dev/null || true
    rm -rf ./* ./.github ./.vscode 2>/dev/null || true
    mkdir -p data assets
    echo "# Data Branch" > README.md
    git add README.md
    git commit -m "chore: initialize data branch"
    git_push_with_retry data
  fi

  mkdir -p data assets
  cp -r "${temp_dir}/data/"* data/ 2>/dev/null || true
  cp "${temp_dir}/assets/file-list.txt" assets/ 2>/dev/null || true

  log "Committing data branch changes"
  git add data/* assets/file-list.txt 2>/dev/null || true
  if git diff --staged --quiet; then
    log "No data branch changes to commit"
  else
    git commit -m "update: ${today} arXiv papers"
  fi
  git_push_with_retry data

  log "Local Docker workflow completed"
}

main "$@"
