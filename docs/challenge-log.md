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