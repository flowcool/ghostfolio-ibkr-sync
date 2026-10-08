# CLAUDE.md — ghostfolio-ibkr-sync

Fork de `obol89/ghostfolio-ibkr-sync`. Cron Python qui sync Interactive Brokers → Ghostfolio.

## Contexte

| Fait | Valeur |
|---|---|
| Fichier principal | `ibkr_to_ghostfolio.py` (~1146 lignes) — mono-fichier par design |
| Dépendances | `requests`, `pyyaml` — garder minimaliste ; `apprise` (+ clôture pinnée) importé uniquement par le worker de notification (`--notify-worker`) |
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
| Tests `pytest` | `tests/` (offline) | `.venv/bin/python -m pytest -q` avant commit ; CI les lance avant le build |
| Hook `pre-commit-compile` | `.claude/hooks/pre-commit-compile.sh` | Avant `git commit` — bloque si syntax error |

Auto-invoke : `code-review` sur diff > 20 lignes, `security-review` si HTTP/XML/env vars touché, `simplify` après fix.

## Git

- Branches : `fix/<sujet>`, `feat/<sujet>`, `refactor/<sujet>`
- Commits : `fix:`, `feat:`, `refactor:`, `chore:` — message court, impératif
- PRs : isolées par concern, merge commit uniquement (squash/rebase désactivés)
- CI: every PR runs pytest, dependency-audit, amd64/arm64 container-check and CodeQL. Required checks gate merges; PRs never publish. See `.github/BUILD.md` for publication refs, main-only latest, weekly refresh and rollback.
- push `staging` → tag `:staging`, tester manuellement avant merge
- Release : après merge, `git tag -a vX.Y.Z <merge-sha>` + push + `gh release create vX.Y.Z --verify-tag --latest` → CI publie `:X.Y.Z` + `:X.Y`. `:latest` reste main-only (un tag d'un vieux commit ne doit pas l'écraser). NAS reste sur `:latest` (décision opérateur 2026-09-30)
- Version : CI `git describe --tags --always` → build-arg `APP_VERSION` → loggée au démarrage (`:latest` affiche `vX.Y.Z-N-g<sha>`)
- Test prod sans écriture : `ssh ugreen 'docker exec -i -e DRY_RUN=1 ghostfolio-ibkr-sync-individual python -' < ibkr_to_ghostfolio.py` (code de la branche, données réelles)

## Findings d'audit

| ID | Sujet | Statut |
|---|---|---|
| A | Corporate actions importées comme trades normaux | Ouvert |
| G | Comment `IBKR#` absent quand Yahoo canonicalise le symbole → re-duplication | Ouvert |
| B,C,D,E,F | Commission abs, sys.exit, SSRF, GBX, DRY_RUN | ✅ mergés (#6–#22) |
| — | Permissions mapping.yaml + error logging | ✅ mergé (#23) |
| — | Upstream merge Ghostfolio 3.x (pagination, isExcluded, exit codes) | ✅ mergé (#24) |
| — | Token IBKR dans les logs (URL requests + urllib3 DEBUG), retry réseau | ✅ mergé (#25, v1.0.0) |
| — | Ventes > 365j ignorées → gate sur holdings Ghostfolio, niveaux de log | ✅ mergé (#27, v1.1.0) |
| — | Revue 2026-09-30 : lecture activités en 1 appel, garde restricted view, dividendes via Cash Transactions, mapping manquant fatal | ✅ mergé (#30–#34) |
| — | Dividendes de positions long-détenues partiellement vendues (perte silencieuse) | ✅ mergé (#35, v2.0.1) |
| — | Revue 2026-10-01 : BUY manuels dédupliqués, isolation exception par compte, suite pytest + CI, README gaps | ✅ mergés (#36–#42, jusqu'à v2.0.3) |
| — | Contexte de sync restauré depuis l'assetProfile Ghostfolio | ✅ mergé (#43, v2.0.4) |
| — | Symbole non résolu bloquait tout l'import du compte → drop-and-retry + exit 1 | ✅ mergé (#44, v2.0.5) |
| — | Dedup dividende sans compte → 2e compte perdait ses dividendes (clé `(accountId, comment)`) | ✅ mergé (#45, v2.0.6) |
| — | Durcissement supply-chain : checksum supercronic + SHAs d'actions pinnés | ✅ mergé (#46, v2.0.7) |
| A, G | Corporate actions : findings fantômes (aucune n'existe dans la query Flex) → reformulés en feature `infra-8tt.29` | Reformulé |

## Gotchas ops

- **Merge ≠ déploiement** : pas de Watchtower sur ugreen ; le conteneur garde l'image du dernier recreate (vu 2026-09-30 : image du 2026-09-22, sans `APP_VERSION`). Après merge : pull + recreate de la stack, puis vérifier la version au log de démarrage
- `mapping.yaml` bind-mount fichier → `docker restart` pour relire après édition hôte
- Collision de ticker : mapper par ISIN (ex. IBKR `TAL`=PetroTal, pas TAL Education)
- Fenêtre Flex = 365j max (limite IBKR). Trade gate (`filter_trades_by_holdings`) : holding Ghostfolio (par compte, ticker résolu) + trades non importés ≥ 0 → import. Ventes ET achats saisis à la main reconnus (même qty ±2j, date la plus proche, fills sommés par jour) → pas de doublon ; un achat ignoré est toujours signalé en WARNING (remède : `IBKR#<tradeID>` dans le commentaire manuel). Position sous un autre symbole même ISIN → WARNING + ligne mapping. Dividendes : aucun filtre fenêtre (un titre long-détenu vendu en partie garde ses dividendes), dédup seule
- Dividendes : source = section Flex **Cash Transactions** (paiements réels + retenue), plus les accruals (`Re` = correction/annulation/paiement → fantômes, #33). Dedup dividende = `dividend#ISIN#date` ou dividende existant même compte+symbole ±3j
- Dedup : `comment='IBKR#<tradeID>'` obligatoire, sinon re-duplication au re-run (finding G)
- GBp/pence : Yahoo cote `.L` en pence (GBp), IBKR reporte en GBP → mismatch ×100 (`gbx_pence_conversion()`, #17)
- PEA devise locale : achat saisi en EUR alors que devise locale → mismatch ≈ taux de change ; convertir `unitPrice` en devise locale
- **Split action/ETF NON géré auto** : transactions restent pré-split, Yahoo renvoie post-split → valo absurde. Corriger : transactions (`quantity*ratio`, `unitPrice/ratio`) + MarketData (close brut non ajusté → `UPDATE "MarketData" SET marketPrice=marketPrice/ratio WHERE date < split`). ⚠️ un re-gather Yahoo peut ré-écraser l'historique pré-split en non-ajusté
- Classification place Yahoo : `.SG`=SICAV, `.PA`=ETF ; `MarketData` keyée par string symbol → purger les orphelines après renommage

## Références

- Fork : https://github.com/flowcool/ghostfolio-ibkr-sync
- Upstream : https://github.com/obol89/ghostfolio-ibkr-sync
- API : `GET /api/v1/activities` (paginated, skip/take), `POST /api/v1/import`, `GET/PUT /api/v1/account/{id}`
- Ghostfolio minimum version: 2.248.0 (activities endpoint); `/api/v1/order` removed in 3.5.0
- Pièges API Ghostfolio (whitelist PUT, restricted view, pagination, drafts) : KB `knowledge-base/bundle/operations/ghostfolio/api-traps.md`
- Upstream remote: `upstream` → https://github.com/obol89/ghostfolio-ibkr-sync (HTTPS, added this session)

## Durable work state

- Epic Beads : `infra-8tt` (ghostfolio) — enfants actifs via `bd list --status=open --metadata-field project=ghostfolio-ibkr-sync`
- Corporate actions : feature `infra-8tt.29` (findings A `infra-8tt.1` + G `infra-cfa` superseded dedans 2026-10-07 — fantômes : aucune corporate action dans la query Flex ; gate = étendre la query IBKR avant de coder)
- Revue de code 2026-09-30 : `bd list --label review-2026-09-30` (ordre porté par les dépendances Beads)
- Revue de code 2026-10-01 : `bd list --label review-2026-10-01` (dividendes long-détenus, achats manuels, suite pytest)
