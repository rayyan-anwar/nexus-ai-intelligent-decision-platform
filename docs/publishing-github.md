# Publishing to GitHub, step by step

Repository name: `nexus-ai-intelligent-decision-platform`.

## 1. Check the contents locally

```bash
unzip nexus-ai-intelligent-decision-platform.zip && cd nexus-ai-intelligent-decision-platform
git status 2>/dev/null || echo "not a git repo yet"        # expected on a fresh unzip
ls -a                                                      # confirm there is NO .env file
grep -rIl --exclude-dir=node_modules -e "BEGIN PRIVATE KEY" -e "password=" . || echo "no obvious secrets"
make test-core                                             # needs: pip install -r backend/requirements-dev.txt
```

## 2. Create the repository

On github.com choose **New repository**, name it `nexus-ai-intelligent-decision-platform`, leave it empty (no README, licence or .gitignore, because the project already has them), and decide public or private.

## 3. Initialise and push

```bash
git init -b main
git add .
git status                                   # review: no .env, no var/, no *.joblib, no node_modules
git commit -m "Initial commit: NEXUS AI intelligent decision platform"
git remote add origin https://github.com/Rayyan21-max/nexus-ai-intelligent-decision-platform.git
git push -u origin main
```

(With SSH use `git@github.com:Rayyan21-max/nexus-ai-intelligent-decision-platform.git`.)

## 4. First CI run

Open the **Actions** tab. The workflow in `.github/workflows/ci.yml` has **never run**. Expect to fix small things on the first pass, most likely:

* `ruff check` findings (`make format` then `cd backend && ruff check --fix .`);
* frontend dependency versions or type errors (`cd frontend && npm install && npm run typecheck && npm run lint`);
* then commit `frontend/package-lock.json` so installs are reproducible, and switch CI's `npm install` to `npm ci`.

Do not add status badges to the README until the workflow is green.

## 5. Repository settings

1. **Settings > Branches**: protect `main` (require pull requests and the CI jobs to pass).
2. **Settings > Code security**: enable Dependabot alerts and security updates, secret scanning, and private vulnerability reporting (referenced from `SECURITY.md`).
3. **About** (gear icon): add a description and topics such as `machine-learning`, `explainable-ai`, `fastapi`, `react`, `typescript`, `mlops`, `anomaly-detection`, `data-drift`.
4. Optional: enable **Discussions** and **Issues** for questions and bug reports.

## 6. Screenshots (genuine ones only)

Run the stack, load the synthetic demo data, train a model, then capture the Overview, Model training, Predictions (showing an uncertainty strip) and Data drift pages. Save them under `docs/screenshots/` and reference them in the README's Screenshots section. Do not use mock-ups.

## 7. First release

After CI is green:

```bash
git tag -a v0.1.0 -m "First release"
git push origin v0.1.0
```

On GitHub choose **Releases > Draft a new release**, pick the tag, and paste the relevant section of `CHANGELOG.md`.
