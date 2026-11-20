## 1. What it does
### 2026-11-10 · Chapter 0 · Workspace Trust in VS Code

- **What happened:** Opening the new project folder showed a "Restricted Mode" banner.
- **What I learned:** VS Code's Workspace Trust opens unfamiliar folders
  read-only. A repo can contain files VS Code acts on automatically: tasks set
  to run on folder open (`.vscode/tasks.json`), workspace settings that point
  to an interpreter or tool path (`.vscode/settings.json`), and extension
  config. Until I trust the folder, tasks and debugging are blocked and
  extensions run in a limited mode, so a cloned repo can't execute code just
  because I opened it.
- **Security call I made:** Trusted this folder, because I created it and it
  contains only my own files. Rule going forward: before trusting any repo I
  didn't write (take-home assignments, cloned projects), check `.vscode/`
  and any task or config files first.
- **Why it matters:** Opening a repo is an attack path on the developer's own
  machine, and malicious repos have targeted developers this way. It's a
  supply-chain control on the laptop, not just the pipeline.
- **Story potential:** maybe. A good supporting point when asked about
  developer-environment or supply-chain security.

  ### 2026-11-10 · Chapter 0 · .gitignore first, and tracked vs untracked files

- **What happened:** Set up the repo and wrote `.gitignore` before the first
  commit, covering OAuth client secrets, tokens, `.env`, `.venv/`, Terraform
  state and kubeconfig.
- **What I learned:**
  - Git sorts files into **untracked** (never committed) and **tracked**
    (committed at least once). `.gitignore` only affects untracked files.
    Once a file is tracked, adding it to `.gitignore` does nothing.
  - Tracking happens in **git, on my laptop**, at `git add`/`git commit`.
    GitHub only sees what I push, but a push sends the full history,
    including earlier commits.
  - So if a secret is committed once and then deleted, it's still in history,
    and the next push sends it to GitHub. `git rm --cached` stops future
    tracking but doesn't remove the old commit.
  - `git add -f` can force-add an ignored file, which is why I also turned on
    push protection as a second layer.
- **How I verified it:** `touch token_test.json` → `git status` didn't list it
  → `git check-ignore -v token_test.json` showed the matching `.gitignore`
  line. `git status` before the first commit showed no secret files.
- **Security call I made:** `.gitignore` before the first commit, with
  secret scanning and push protection on before the first push. Prevention
  is cheap; for a leaked secret, the fix is rotation, not deletion.
- **Story potential:** maybe. Useful for "how do you prevent secrets in
  repos?", backed by my secret-scanning work.

 # Design review: drive-sync

**Date:** 2026-11-11 · **Author:** Prashasti · **Status:** pre-build (revisit in Chapter 7)

## 1. What it does
Files from Team A's Drive are copied to Team B's Drive. Team A owns the
originals and Team B holds the copies. The files could contain sensitive
information and cross an access boundary, so a stolen credential or a copy
landing in the wrong account would be a data leak. This lab uses dummy data
and test accounts only.

## 2. Components
**Application layer**
- **Drive A (test account A / Team 1):** source folder; holds the originals
- **Drive B (test account B / Team 2):** destination; holds the copies
- **Sync job (Python):** lists, downloads and uploads new or changed files
- **Google OAuth client + server:** identifies the app; issues tokens after consent
- **Tokens:** refresh token A (`drive.readonly`), refresh token B (`drive.file`)
- **Token storage:** laptop file outside repo → Kubernetes Secret → AWS Secrets Manager
- **Logs:** one line per copy attempt

**Platform layer**
- **GitHub repo + Actions:** code, build, scans, CI gate
- **Container image + registry:** loaded into kind locally, pushed to ECR for EKS
- **Kubernetes:** kind locally, EKS on AWS; runs the job as a CronJob
- **AWS IAM (IRSA / Pod Identity) + Terraform:** who may read the tokens; creates the AWS pieces

## 3. Data flow
1. Job starts on a schedule.
2. Job loads its tokens from storage.
3. Job exchanges them with Google for short-lived access.
4. Using token A, it lists files in the source folder.
5. Using token B, it checks whether each file was already copied or has changed.
6. Using token A, it downloads new or changed files.
7. Using token B, it uploads the copy, tagged with the original's ID.
8. It logs name, time and result. Never tokens or file contents.

**Key point:** Drive A and Drive B never connect directly. The job holds both
tokens, so the job and its token storage are the most valuable target.

## 4. Trust boundaries
1. **Drive A → job:** files and names enter the job; whoever controls Drive A controls this input
2. **Job → Drive B:** data leaves into the other team's account
3. **Job ↔ Google OAuth:** credentials sent over the internet
4. **Token storage → pod:** AWS IAM (EKS) or Kubernetes RBAC (kind) decides who reads the tokens
5. **Repo / CI → cluster:** whatever the pipeline builds runs with both tokens
6. **Internet → EKS API endpoint:** who can reach the cluster's control plane

## 5. Assets (top 3)
1. Refresh token A: reads **all** of Drive A, not just the folder
2. Refresh token B: writes into Drive B
3. File contents in transit

## 6. Threats and planned controls
| # | Threat | STRIDE | Planned control | Ch |
|---|---|---|---|---|
| 1 | Token A stolen; attacker reads all of Drive A | I | Dedicated test account, dummy data; token outside repo (0600) → K8s Secret → Secrets Manager + IRSA; revoke on suspicion | 1, 3, 6 |
| 2 | Token B stolen; attacker writes into Drive B | T | `drive.file` scope: app sees only files it created | 1 |
| 3 | Malicious file names or contents from Drive A (path tricks, fake log lines, huge files) | T, D | Files handled in memory, no local paths; JSON logs; size limit; unsupported types skipped | 1 |
| 4 | Token issued for the wrong account; copies leak to the wrong place | I | Startup check: token emails must match expected accounts, and source ≠ destination | 1 |
| 5 | Secrets end up in the repo, image or logs | I | `.gitignore`, push protection, no secrets in image layers, logs never include tokens or contents | 0, 1, 2 |
| 6 | Duplicates or missed updates | T | State tags on copies in B; checksum check | 1 |
| 7 | Compromised dependency, base image or GitHub Action runs with both tokens | T, E | Pinned dependencies, digest-pinned base image, Trivy, SHA-pinned actions, SBOM + signing, Dependabot | 2, 5 |
| 8 | Pod compromised; attacker reaches K8s API, tokens, node role or internet | E, I | Non-root, securityContext, no auto-mounted SA token, minimal RBAC, NetworkPolicy (tested), IRSA, IMDSv2 hop limit 1 | 3, 6 |
| 9 | Over-broad AWS access to the secret, or tokens leak into Terraform state | I, E | IAM limited to one secret ARN; token value set outside Terraform or write-only; Checkov | 4 |
| 10 | EKS API exposed, or cloud left running | S, D | API endpoint restricted to my IP; budget alert; teardown checklist | 6 |

## 7. Assumptions and out of scope
- Google's and AWS's own infrastructure are trusted.
- My laptop is trusted for development.
- Deletes in Drive A are **not** copied to B (a decision, not a bug).
- Single-owner repo; no team access controls in this lab.

## 8. Open questions
- Account B: Google blocked creation. Retry, or use a low-risk fallback (B only gets `drive.file`).
- Google "Testing" mode refresh tokens expire after 7 days. Does that affect the 2–3 day EKS run?
- Does kind's network plugin actually enforce NetworkPolicy? (Test in Ch 3.)

### 2026-11-13 · Chapter 1 · OAuth library uses PKCE and state

- **Question:** Does google-auth-oauthlib's InstalledAppFlow use PKCE and
  state, or do I have to add them?
- **How I checked:** Read the authorization URL the script printed when I ran
  `python -m src.authorize --account dest`.
- **What I found:** The URL includes `state=<random value>` (CSRF protection
  on the callback) and `code_challenge=…&code_challenge_method=S256` (PKCE,
  so an intercepted authorization code can't be redeemed by someone else).
- **What I learned:** Verify a library's security behaviour from evidence,
  not assumptions. Here the library handles both by default.
- **Story potential:** yes. "I verified PKCE and state in the actual
  authorization request rather than assuming the library did it."

   ### 2026-11-14 · Chapter 1 · Account-mismatch guard tested
   - **Control:** sync.py checks each token's email (from Google) against
     the expected accounts in .env and stops before any file is touched.
   - **Test:** set EXPECTED_SOURCE_EMAIL to the wrong account → STOP message,
     non-zero exit code. Correct settings → "Tokens OK".
   - **Why it matters:** Google enforces what a token can do, not which
     account I meant. Only my code knows the intent.
   - **Story potential:** yes. "I tested the control by breaking it."

      ### 2026-11-17 · Chapter 1 · F3 test caught a silent duplicate bug
   - **What happened:** the second run copied every file again.
   - **Cause:** the tag key written on upload didn't match the key
     searched for in find_copy, so no copy was ever "found". No error,
     just duplicates.
   - **Fix:** made both use source_file_id; cleared Drive B; reran.
   - **Result:** run 1 COPIED ×4, run 2 ALREADY COPIED ×4 (F1, F3 pass).
   - **Lesson:** "it ran without errors" isn't a test. Test the
     behaviour (run twice, check for duplicates).
   - **Story potential:** yes

   ### 2026-11-20 · Chapter 2 · Hardening the container image

- **Goal:** take a naive first image, scan it, harden it, scan again (S2, S3).

- **Before (v1: `FROM python:3.12`, `COPY . .`, runs as root):**
  - 2.09 GB on disk
  - 528 high/critical CVEs (527 OS, 1 Python: setuptools from the base image), 16 critical
  - Running as root (Trivy DS-0002, HIGH)
  - `.env`, `.git` and `.venv` baked into the image: no `.dockerignore`, and
    Docker doesn't read `.gitignore`
  - Tokens were NOT in the image: they live in `~/.drive-sync`, outside the
    repo folder, so they were never in the build context

- **What I changed:**
  - `python:3.12-slim`, pinned by `@sha256` digest
  - `.dockerignore` (`.git`, `.venv`, `.env*`, `**/__pycache__`, docs…)
  - Explicit copy: only `requirements.txt`, `src/__init__.py`, `src/sync.py`
    (allowlist, not denylist)
  - `pip install --no-cache-dir`
  - Unprivileged `appuser` (UID 10001); app files stay root-owned and read-only
  - Tokens mounted read-only at run time, never copied into the image

- **After (v2):**
  - 398 MB (−81%)
  - 48 high, 0 critical (−91%), all in the Debian base OS; 0 in my Python
    dependencies
  - Only 1 of the 48 has an upstream fix; the rest are accepted until fixes
    ship, with rescans and base-digest updates
  - `whoami` → appuser; `/app` holds only the three files the job needs
  - Sync still runs end to end (regression check after each change)

- **Triage notes:**
  - Most v1 findings were packages the job never uses (MariaDB, OpenSSH, wget,
    Perl, X11, build headers). The fix was removing them, not patching them
  - `linux-libc-dev` kernel CVEs are mostly noise in a container: it uses the
    host's kernel
  - DS-0026 (no HEALTHCHECK, LOW): accepted, not applicable to a batch job
  - Scoped `trivy config` with `--skip-dirs .venv`: the unscoped scan reported
    hundreds of .venv JSON files as CloudFormation, all noise

- **What broke / surprised me:**
  - Digest pasted as `sha256:sha256:…` → "invalid reference format"
  - First tidy attempt (`authorize.py/` in .dockerignore) didn't match
    `src/authorize.py`; fixed with an explicit COPY list
  - The destination token expired 7 days after consent (Testing-mode OAuth);
    the container failed closed with one `auth_failed` log line. Re-authorized
    on my Mac

- **What I learned:**
  - Docker ignores `.gitignore`; only `.dockerignore` and what you COPY count
  - Layers are permanent: rebuilding doesn't un-leak a secret in a pushed image
  - The scanner flagged root but not `.env` in the image; I found that by
    inspecting the image myself

- **Story potential:** yes. "2.09 GB and 528 high/critical CVEs → 398 MB and
  48, zero in my own dependencies, only one fixable, non-root, nothing in the
  image but the code."