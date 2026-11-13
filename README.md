# drive-sync: a cloud-native security lab

A small service that copies new or changed files from one Google Drive account to another, built as a hands-on lab for **container, Kubernetes, Terraform and CI/CD security**.

> **Personal lab, dummy data only.** Account A is a dedicated test account holding fictional files. This is not production experience and makes no production claims.

## The scenario

Two teams can't see each other's Drive, so files move between them by hand. drive-sync watches a folder in **Drive A (Team 1)** and copies new or updated files into **Drive B (Team 2)**.

Moving files across an access boundary is effectively a data-exfiltration channel. That makes every design choice a security choice: OAuth scopes, where tokens live, what identity the job runs as, what the cluster allows, and what the pipeline blocks.

## How it works

```
Drive A ──list / download──▶  SYNC JOB  ──check / upload──▶ Drive B
(source)   token A           (holds both     token B        (copies)
           read-only           tokens)       per-file only
                                  ▲
                                  │ reads tokens at start
           Token storage: local file → Kubernetes Secret → AWS Secrets Manager
```

Drive A and Drive B never connect directly. Every byte passes through the job, which holds both accounts' tokens. That makes the job and its token storage the most valuable target, and the design is built around protecting them.

## Roadmap

| # | Chapter | What gets built | Status |
|---|---|---|---|
| 0 | Setup and design review | Repo, test account, dummy files, challenge log, one-page design review | ✅ Done |
| 1 | Deterministic sync and code review | OAuth setup, sync script, manual secure code review | 🟡 In progress |
| 2 | Container | Hardened Docker image, Trivy scan | ⬜ |
| 3 | Kubernetes (local) | CronJob on kind, securityContext, RBAC, NetworkPolicy, "attack your own pod" | ⬜ |
| 4 | Terraform | Secrets Manager, least-privilege IAM, ECR, Checkov | ⬜ |
| 5 | CI/CD | GitHub Actions gate: image, manifest and IaC scans, CodeQL, SBOM and signing | ⬜ |
| 6 | AWS deployment | EKS for a 2–3 day run with IRSA and IMDSv2, then full teardown | ⬜ |
| 7 | Threat model and review | STRIDE across the built system; which scanner findings were real | ⬜ |
| 8 | AI guardrail and eval | Rules + LLM sensitivity check, labelled eval, prompt-injection test | ⬜ |

## Security decisions so far

- **Least-privilege OAuth scopes.** The source token is read-only (`drive.readonly`). The destination token uses `drive.file`, so the app can only see files it created itself.
- **Secrets never touch the repo.** OAuth client and tokens live in `~/.drive-sync/`, outside the repo, with `0600` permissions set at creation.
- **Verify identity, don't trust labels.** A scope doesn't say *which* account it belongs to, so the code asks Google whose token it is.
- **Repo protection on before the first push.** Secret scanning, push protection and Dependabot security updates enabled via the GitHub API.
- **Pinned dependencies** in `requirements.txt`.

Reasoning for each decision lives in [`docs/decisions.md`](docs/decisions.md).

## How it's verified

Each requirement has a test that says when it's met.

**Functional**

| ID | Requirement | Test |
|---|---|---|
| F1 | A new file in A appears in B | Add a file, run the job, confirm the copy |
| F2 | A changed file is updated in B | Edit the file, confirm the new version arrives |
| F3 | Nothing is copied twice, with state kept outside the pod | Run the job twice, confirm no duplicates |
| F4 | Every copy attempt is logged (name, time, outcome) | Read the log after a run |
| F5 | Runs on a schedule, not as a long-running server | Kubernetes CronJob fires on its interval |
| F6 | Same image and manifests run on kind and EKS | Deploy to both, diff the configuration |
| F7 | Runs on EKS for 2–3 days without manual fixes | Check job history and logs at the end |

**Security**

| ID | Requirement | Test |
|---|---|---|
| S1 | Minimum OAuth scopes | Review the consent screens and token scopes |
| S2 | No secret in the repo, image or manifests | Secret scan passes; image history is clean |
| S3 | Non-root container, pinned base image | Inspect the Dockerfile; `whoami` in the container |
| S4 | Pod security context, limits, restricted service account | Manifest scan has no unexplained high findings |
| S5 | Tokens in a secret store created by Terraform, least-privilege IAM | Checkov clean or explained; token not in Terraform state |
| S6 | CI fails on high-severity findings | A deliberately bad change fails the pipeline |
| S7 | Actions pinned to SHAs, minimal permissions | Review the workflow file |
| S8 | Pod reads secrets via IRSA / Pod Identity, no static keys | Review IAM role and pod config |
| S9 | EKS API endpoint restricted to my IP | Terraform + Checkov |
| S10 | Budget alert before any AWS resource; verified teardown | Alert visible; leftover checklist clear |

## Running it locally

**Prerequisites:** Python 3, a Google Cloud project with the Drive API enabled, a Desktop OAuth client, and both accounts added as test users.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# OAuth client JSON goes outside the repo
mkdir -p ~/.drive-sync && chmod 700 ~/.drive-sync
mv ~/Downloads/client_secret_*.json ~/.drive-sync/client_secret.json
chmod 600 ~/.drive-sync/client_secret.json

# One consent per account; check the printed email each time
python -m src.authorize --account source   # sign in as account A
python -m src.authorize --account dest     # sign in as account B
```

The sync script (`src/sync.py`) is being built in Chapter 1.

## Repo layout

```
drive-sync/
├── src/
│   └── authorize.py        # one-time OAuth consent per account
├── docs/
│   ├── design-review.md    # pre-build: data flow, trust boundaries, threats, controls
│   ├── decisions.md        # what I decided and why
│   └── challenge-log.md    # what broke, what I learned
├── dummy-files/            # fictional test files
├── requirements.txt
└── .gitignore
```

## Docs

- [Design review](docs/design-review.md): components, data flow, six trust boundaries, ten threats with planned controls
- [Decisions](docs/decisions.md)
- [Challenge log](docs/challenge-log.md)

---

I'm building this with AI coding tools for the first versions and reviewing every part myself. The goal is to be able to explain each line and each security decision.