# Local Docker Runner

This repo can run locally in Docker instead of GitHub Actions while still pushing
generated updates back to GitHub.

## Files

- `Dockerfile`: builds the Python/uv/git runtime.
- `docker-compose.yml`: runs the image with the repository mounted read-only at
  `/app`.
- `.env.docker.example`: environment variable template.
- `scripts/local-docker-workflow.sh`: non-interactive local replacement for the
  GitHub Actions workflow.

## Setup

1. Copy the env template:

   ```bash
   cp .env.docker.example .env.docker
   ```

2. Edit `.env.docker`:

   - `OPENAI_API_KEY`
   - `OPENAI_BASE_URL`
   - `MODEL_NAME`
   - `LANGUAGE`
   - `CATEGORIES`
   - `EMAIL`
   - `NAME`
   - `REPO_OWNER`
   - `REPO_NAME`

3. Configure push authentication.

   Recommended: keep `origin` as an SSH remote. This repository's
   `docker-compose.yml` already mounts these Windows SSH key files read-only
   into the container:

   - `C:\Users\24761\.ssh\id_ed25519`
   - `C:\Users\24761\.ssh\id_ed25519.pub`

   ```yaml
   volumes:
     - .:/app:ro
     - /mnt/c/Users/24761/.ssh/id_ed25519:/run/host-ssh/id_ed25519:ro
     - /mnt/c/Users/24761/.ssh/id_ed25519.pub:/run/host-ssh/id_ed25519.pub:ro
   ```

   Alternative: set `GIT_PUSH_TOKEN` in `.env.docker`. The token needs write
   access to this repository.

4. Build the image:

   ```bash
   docker compose build
   ```

## Run

Make sure the repository is on `main` and the worktree is clean. The runner
refuses to start with uncommitted changes unless `ALLOW_DIRTY_WORKTREE=true`.
The container clones the committed branch into a temporary directory and runs
there, so your local checkout is not switched to the `data` branch. If you set
`ALLOW_DIRTY_WORKTREE=true`, uncommitted files are still not included in that
temporary clone.

```bash
docker compose run --rm arxiv-runner
```

The container will:

1. clone the clean source branch into `/tmp`;
2. install/sync Python dependencies with `uv`;
3. crawl arXiv for the UTC date;
4. deduplicate against recent local data;
5. optionally filter papers by topic;
6. run AI enhancement;
7. convert to Markdown;
8. update `assets/file-list.txt`;
9. inject `js/auth-config.js` and `js/data-config.js`;
10. commit config changes to `main`;
11. commit data files to the `data` branch;
12. push both branches.

## Scheduling

Use cron, Windows Task Scheduler, or any local scheduler. Example cron entry:

```cron
30 9 * * * cd /path/to/robotics-daily-arXiv && docker compose run --rm arxiv-runner >> docker-run.log 2>&1
```

## Useful Overrides

- `RUN_DATE=YYYY-MM-DD`: rerun for a specific date.
- `AI_MAX_WORKERS=6`: set AI enhancement concurrency. Increase carefully if
  responses are slow; lower it if the provider rate-limits.
- `AI_REQUEST_RETRIES=3`: retry each failed AI request this many times before
  falling back to default fields.
- `AI_RETRY_BASE_SECONDS=2`: initial retry backoff.
- `AI_RETRY_MAX_SECONDS=60`: maximum retry backoff.
- `AI_REQUEST_STAGGER_SECONDS=0.5`: add small random start jitter per request to
  reduce bursty traffic.
- `TOPIC_FILTER_ENABLED=true`: use an LLM to classify crawled papers against
  your research scope before AI enhancement.
- `TOPIC_FILTER_MODEL_NAME=...`: optional classifier model override. Empty means
  use `MODEL_NAME`.
- `TOPIC_FILTER_MAX_WORKERS=6`: classifier concurrency. Keep it at or below
  `AI_MAX_WORKERS` if the provider rate-limits.
- `TOPIC_FILTER_MIN_CONFIDENCE=0.65`: low-confidence rejections are treated as
  uncertain.
- `TOPIC_FILTER_KEEP_UNCERTAIN=true`: keep uncertain rejections to reduce false
  negatives.
- `TOPIC_FILTER_SCOPE=...`: natural-language description of your research scope,
  e.g. embodied AI, VLA, world model/action, robot learning, manipulation,
  locomotion, navigation, autonomous driving agents, sim-to-real, physical AI,
  robot foundation models, and related benchmarks.
- `TOPIC_FILTER_REQUEST_RETRIES=3`: retry each failed classifier request this
  many times.
- `TOPIC_FILTER_REQUEST_STAGGER_SECONDS=0.5`: add small random start jitter per
  classifier request to reduce bursty traffic.
- `PUSH_CHANGES=false`: run the pipeline without committing or pushing. Because
  generation happens in a temporary clone, set `KEEP_RUN_DIR=true` too if you
  want to inspect the generated files.
- `ALLOW_DIRTY_WORKTREE=true`: bypass the clean-worktree guard.
- `KEEP_RUN_DIR=true`: keep the temporary clone for debugging.

## Troubleshooting

If `docker compose build` fails while resolving `deb.debian.org`, Docker itself
cannot reach Debian package mirrors. Configure Docker Desktop / Docker daemon to
use your proxy or a working DNS server, then rebuild. This is an environment
network issue rather than a project dependency issue.
