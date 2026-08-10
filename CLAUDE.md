# CLAUDE.md — ghostfolio-ibkr-sync

Fork de `obol89/ghostfolio-ibkr-sync`. Cron Python qui sync Interactive Brokers → Ghostfolio.

## Contexte

| Fait | Valeur |
|---|---|
| Fichier principal | `ibkr_to_ghostfolio.py` (~727 lignes) — mono-fichier par design |
| Dépendances | `requests`, `pyyaml` — garder minimaliste |
| Runtime | `python:3.12-slim` + supercronic, cron `5 6 * * *` |
| Image | `ghcr.io/flowcool/ghostfolio-ibkr-sync:latest` |
| Déployé sur | UGreen NAS (192.168.2.117), stack ghostfolio Portainer |
| Ghostfolio | `http://ghost:3333` (réseau Docker interne) |

## Skills & rules

| Primitive | Fichier | Trigger |
|---|---|---|
| Rule `python-conventions` | `.claude/rules/python-conventions.md` | Auto quand `*.py` touché |
| Rule `security` | `.claude/rules/security.md` | Toujours chargée |
| Skill `/review-pr` | `.claude/skills/review-pr/` | Manuel — obligatoire avant merge |
| Skill `/test-sync` | `.claude/skills/test-sync/` | Manuel |
| Hook `pre-commit-compile` | `.claude/hooks/pre-commit-compile.sh` | Avant `git commit` — bloque si syntax error |

Auto-invoke : `code-review` sur diff > 20 lignes, `security-review` si HTTP/XML/env vars touché, `simplify` après fix.

## Git

- Branches : `fix/<sujet>`, `feat/<sujet>`, `refactor/<sujet>`
- Commits : `fix:`, `feat:`, `refactor:`, `chore:` — message court, impératif
- PRs : isolées par concern, merge commit uniquement (squash/rebase désactivés)
- CI : push `main` → build amd64+arm64 → `ghcr.io/flowcool/ghostfolio-ibkr-sync:latest`
- push `staging` → tag `:staging`, tester manuellement avant merge

## Findings d'audit

| ID | Sujet | Statut |
|---|---|---|
| A | Corporate actions importées comme trades normaux | Ouvert |
| G | Comment `IBKR#` absent quand Yahoo canonicalise le symbole → re-duplication | Ouvert |
| B,C,D,E,F | Commission abs, sys.exit, SSRF, GBX, DRY_RUN | ✅ mergés (#6–#22) |
| — | Permissions mapping.yaml + error logging | ✅ mergé (#23) |
| — | Upstream merge Ghostfolio 3.x (pagination, isExcluded, exit codes) | ✅ mergé (#24) |

## Gotchas ops

- `mapping.yaml` bind-mount fichier → `docker restart` pour relire après édition hôte
- Collision de ticker : mapper par ISIN (ex. IBKR `TAL`=PetroTal, pas TAL Education)

## Références

- Fork : https://github.com/flowcool/ghostfolio-ibkr-sync
- Upstream : https://github.com/obol89/ghostfolio-ibkr-sync
- API : `GET /api/v1/activities` (paginated, skip/take), `POST /api/v1/import`, `GET/PUT /api/v1/account/{id}`
- Ghostfolio minimum version: 2.248.0 (activities endpoint); `/api/v1/order` removed in 3.5.0
- Upstream remote: `upstream` → https://github.com/obol89/ghostfolio-ibkr-sync (HTTPS, added this session)
