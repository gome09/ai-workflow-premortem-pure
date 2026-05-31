# Open Source Release Checklist

> **Target release:** `v0.8.0-beta.1-local-preview-final`
> **Source version:** `0.8.0-alpha.11`

---

## 1. Repository Setup

### 1.1 Create a New GitHub Repository

**Do NOT push this over the first public edition.**

Create a new, separate GitHub repository for this second edition:

- [ ] Create a new repository (e.g., `ai-workflow-premortem-pure` or similar)
- [ ] Do NOT force-push or overwrite the first edition repository
- [ ] Confirm the first edition repository remains intact and accessible

### 1.2 Push Initial Content

```bash
git init
git remote add origin https://github.com/LucasTydney/ai-workflow-premortem-pure.git
git add .
git commit -m "Second public edition: v0.8.0-beta.1-local-preview-final"
git push -u origin main
```

### 1.3 Create the Release Tag

```bash
git tag -a v0.8.0-beta.1-local-preview-final -m "Second public edition: local-preview final"
git push origin v0.8.0-beta.1-local-preview-final
```

---

## 2. GitHub Repository Settings

### 2.1 Security Settings

Navigate to **Settings → Code security and analysis** and enable:

- [ ] **Secret scanning** — detect committed secrets automatically
- [ ] **Push protection** — block pushes that contain detected secrets
- [ ] **Dependabot alerts** — receive alerts for vulnerable dependencies
- [ ] **Dependabot security updates** — automatic PRs for security patches

### 2.2 General Settings

- [ ] Confirm repository visibility (public or private as intended)
- [ ] Add repository description and topics
- [ ] Link to the project website or documentation if applicable

---

## 3. Credential Audit

### 3.1 Confirm No Real Credentials Are Committed

```bash
# Check for .env files
git ls-files | grep -i '\.env'

# Check for API key patterns
git log --all --diff-filter=A --name-only -- '*.env' '*.env.*'
```

- [ ] No `.env` files in version control
- [ ] No real DeepSeek API keys in any commit
- [ ] No real Tavily API keys in any commit
- [ ] No real database passwords in any commit
- [ ] `.gitignore` includes `.env` and `.env.*` patterns

### 3.2 Confirm .env.example Exists

- [ ] `.env.example` is present with placeholder values
- [ ] `.env.example` documents all required environment variables

---

## 4. Documentation Visibility

### 4.1 README

- [ ] Local-preview limitations are visible in README
- [ ] "NOT production-ready" is stated clearly
- [ ] Quick start instructions are accurate

### 4.2 SECURITY.md

- [ ] Security policy is present and current
- [ ] Local-preview limitations are listed
- [ ] Vulnerability reporting instructions are clear

### 4.3 Release Notes

- [ ] Release tag description includes local-preview disclaimer
- [ ] Release notes reference SECURITY.md and known limitations

### 4.4 Second Edition

- [ ] `SECOND_EDITION.md` is present and explains the edition relationship

---

## 5. CI/CD

### 5.1 GitHub Actions

- [ ] `.github/workflows/test.yml` runs on push and PR
- [ ] Tests pass in CI

### 5.2 Dependabot

- [ ] `.github/dependabot.yml` is configured for weekly updates
- [ ] Covers: `uv`, `github-actions`, `docker`

---

## 6. Collaboration Templates

- [ ] `.github/ISSUE_TEMPLATE/bug_report.yml` is present
- [ ] `.github/ISSUE_TEMPLATE/feature_request.yml` is present
- [ ] `.github/ISSUE_TEMPLATE/config.yml` is present
- [ ] `.github/PULL_REQUEST_TEMPLATE.md` is present

---

## 7. Final Confirmation

- [ ] All acceptance evidence is in `artifacts/full_acceptance_latest_minimal/`
- [ ] `CLAUDE.md` constraints are current
- [ ] `CONTRIBUTING.md` is present
- [ ] `SUPPORT.md` is present
- [ ] `LICENSE` is present (MIT)
- [ ] First edition repository is untouched

---

## Post-Release

After publishing:

1. Monitor Dependabot PRs weekly
2. Respond to issues on a best-effort basis
3. Do not claim production readiness in any communication
4. Direct users to the first edition if they need that version
