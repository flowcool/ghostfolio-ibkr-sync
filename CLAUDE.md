# CLAUDE.md — ghostfolio-ibkr-sync

Fork de `obol89/ghostfolio-ibkr-sync`. Cron Python qui sync Interactive Brokers → Ghostfolio.

## 1. Contexte projet

| Fait | Valeur |
|---|---|
| Fichier principal | `ibkr_to_ghostfolio.py` (~727 lignes) — **mono-fichier par design** (volume-mount Docker facile) |
| Dépendances | `requests`, `pyyaml` — minimaliste, garder ainsi |
| Runtime | `python:3.12-slim` + supercronic, cron `5 6 * * *` |
| Image produite | `ghcr.io/flowcool/ghostfolio-ibkr-sync:latest` — build auto CI sur push `main` |
| Déployé sur | UGreen NAS (192.168.2.117), stack ghostfolio Portainer |
| Lien infra | Se connecte à Ghostfolio via `http://ghost:3333` (réseau Docker interne) |

**Ce que fait le script :**
1. Flex Query IBKR (2 étapes HTTP) → XML trades + dividendes + cash balance
2. `GET /api/v1/activities` Ghostfolio → déduplication par `IBKR#{tradeID}` et `dividend#{isin}#{date}`
3. `POST /api/v1/import` → nouvelles activités uniquement
4. `PATCH /api/v1/account/{id}` → cash balance

## 2. Skills (auto-invocation)

| Skill | Auto-trigger |
|---|---|
| `code-review` | Tout diff > 20 lignes ou nouvelle fonction / modification logique de dédup ou d'import |
| `security-review` | Toute modification touchant : appels HTTP externes, parsing XML, lecture env vars, credentiels |
| `simplify` | Après un fix fonctionnel, si le code autour semble dense ou redondant |
| `verify` | Après tout fix sur la dédup ou l'import — confirmer via docker exec ou run manuel |

## 3. Sous-agents — quand les utiliser

```
Explore      → recherche large dans ibkr_to_ghostfolio.py (patterns, call sites, toutes les utilisations d'une variable)
Agent(sécurité) → review indépendante avant tout nouvel appel HTTP externe ou parsing d'input externe
                  prompt : "Review this function for SSRF, injection, and credential leak risks. Code: ..."
```

Ne pas spawner d'agent pour des lookups ponctuels — utiliser grep/Read directement.

## 4. Principes de travail

**Python**
- Style existant : pas de type hints, logging `log.warning/error/debug`, pas de classes
- Mono-fichier : ne pas créer de modules supplémentaires sans raison forte
- Pas de test suite : les tests sont manuels (voir § 6)
- Erreurs : `raise RuntimeError(...)` avec message explicite, jamais `return` silencieux sur failure
- Logging : `log.warning` pour les skips opérationnels, `log.error` pour les failures, ne jamais logger un token

**Sécurité (mindset permanent)**
- SSRF connu (finding D) : `base_url` step-2 IBKR vient du XML IBKR — assertion de préfixe à ajouter
- XML : `ET.fromstring` ok (pas d'XXE avec ElementTree), mais valider les champs extraits
- Credentials (`IBKR_TOKEN`, `GHOST_TOKEN`) : uniquement depuis `os.environ`, jamais hardcodés ni loggés
- Tout nouvel appel HTTP externe → déclencher `security-review`

**Git**
- Branches : `fix/<sujet>`, `feat/<sujet>`, `refactor/<sujet>`
- Commits : `fix:`, `feat:`, `refactor:`, `chore:` — message court, impératif
- PRs : isolées par concern, une PR = un fix
- CI build l'image sur push `main` → pas de tag manuel nécessaire pour `latest`

## 5. Findings d'audit ouverts (à traiter par priorité)

| ID | Sujet | Priorité |
|---|---|---|
| D | SSRF : `base_url` step-2 IBKR pris tel quel depuis XML | Haute |
| A | Corporate actions importées comme trades normaux | Moyenne |
| C | `sys.exit(1)` dans `ghost_find_account_id()` — non testable | Basse |
| B | `abs(commission)` swallows rebates positifs | Basse |

## 6. Tester le script

```bash
# Run manuel hors cron (container existant)
docker exec ghostfolio-ibkr-sync-individual python /app/ibkr_to_ghostfolio.py

# Run local direct (nécessite les env vars)
export IBKR_TOKEN=... GHOST_TOKEN=... GHOST_HOST=http://... IBKR_ACCOUNT_IDS=... IBKR_QUERY_IDS=...
python ibkr_to_ghostfolio.py

# Vérifier l'image courante sur le NAS
docker inspect ghostfolio-ibkr-sync-individual --format '{{.Config.Image}}'

# Logs du dernier run cron
docker logs ghostfolio-ibkr-sync-individual --tail 50
```

**Pas de mock, pas de fixture** — le script est stateless et idempotent (dédup côté Ghostfolio).
Tester avec les vraies APIs en mode lecture d'abord (`GET /api/v1/activities`), puis valider l'import sur un compte de test si possible.

## 7. CI / déploiement

```
push main → GitHub Actions build linux/amd64 + linux/arm64
           → push ghcr.io/flowcool/ghostfolio-ibkr-sync:latest
           → Portainer poll repo infra → redéploie le container
```

Pour switcher vers l'image du fork (à faire après merge des 5 PRs) :
- Changer `image:` dans `infra/repo/stacks/ugreen/ghostfolio/docker-compose.yml`
- Supprimer le volume workaround `ibkr_to_ghostfolio.py`

## 8. Références

- Fork : https://github.com/flowcool/ghostfolio-ibkr-sync
- Upstream : https://github.com/obol89/ghostfolio-ibkr-sync
- Ghostfolio API : `GET /api/v1/activities`, `POST /api/v1/import`, `GET /api/v1/account/{id}`
- 5 PRs ouvertes (merger dans l'ordre #1→#2→#3→#4→#5) — voir infra `claude/projects/IBKR_SYNC_FORK.md`
