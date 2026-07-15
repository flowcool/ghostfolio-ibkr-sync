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

### Review externe obligatoire avant merge (anti-biais auteur)

**Règle** : toute PR doit passer par un `code-reviewer` sub-agent *avant* d'être considérée prête. L'agent démarre sans contexte de la conversation → pas de biais auteur.

Lancer en parallèle pour un lot de PRs :

```python
Agent(
    subagent_type="everything-claude-code:code-reviewer",
    run_in_background=True,
    prompt="""Review this Python diff cold (no prior context).
Context: single-file sync script, requests+yaml, raise RuntimeError on failure.
Diff: <coller git diff main...origin/branch>
Report: correctness bugs only, skip style. Be concise."""
)
```

**Checklist spécifique à ce repo** (points historiquement manqués) :
- Dockerfile : pas de `VOLUME` dupliqué, `chown` avant `VOLUME`
- Python guards : si guard ajouté à l'appel, vérifier que le callee n'a pas le même (dead code)
- `except` scope : vérifier que le type d'exception capturé couvre bien ce que la fonction peut lever (`RuntimeError` ne couvre pas `requests.RequestException`)
- Deferred raise : si on diffère une exception pour laisser du code s'exécuter, vérifier que les valeurs de retour ne sont pas perdues

**Après la review sub-agent — documenter dans la PR :**
```bash
gh pr comment <N> --repo flowcool/ghostfolio-ibkr-sync --body "## Review sub-agent (YYYY-MM-DD)
<findings et corrections>"
```
C'est la source de vérité durable : attachée au code, visible dans l'historique GitHub, indépendante de CLAUDE.md.

**CodeRabbit — second avis optionnel, 1 PR à la fois :**
- Nouvelles PRs : auto-reviewées à la création (`.coderabbit.yaml`)
- PRs existantes : trigger `@coderabbitai review` **1 seule PR à la fois**, juste avant de merger
- ⚠️ Ne jamais bulk-trigger — rate limit horaire atteint immédiatement au-delà de ~5 PRs

## 4. Principes de travail

**Python**
- Style existant : pas de type hints, logging `log.warning/error/debug`, pas de classes
- Mono-fichier : ne pas créer de modules supplémentaires sans raison forte
- Pas de test suite : les tests sont manuels (voir § 6)
- Erreurs : `raise RuntimeError(...)` avec message explicite, jamais `return` silencieux sur failure
- Logging : `log.warning` pour les skips opérationnels, `log.error` pour les failures, ne jamais logger un token

**Sécurité (mindset permanent)**
- SSRF (finding D) : assertion de préfixe sur `base_url` step-2 IBKR — **fixé (PR #6)**
- XML : `ET.fromstring` ok (pas d'XXE avec ElementTree), mais valider les champs extraits
- Credentials (`IBKR_TOKEN`, `GHOST_TOKEN`) : uniquement depuis `os.environ`, jamais hardcodés ni loggés
- Tout nouvel appel HTTP externe → déclencher `security-review`

**Git**
- Branches : `fix/<sujet>`, `feat/<sujet>`, `refactor/<sujet>`
- Commits : `fix:`, `feat:`, `refactor:`, `chore:` — message court, impératif
- PRs : isolées par concern, une PR = un fix
- Merge strategy : merge commit uniquement (squash et rebase désactivés sur GitHub) — évite la divergence staging/main
- CI build l'image sur push `main` → pas de tag manuel nécessaire pour `latest`

## 5. Findings d'audit

| ID | Sujet | Priorité | Statut |
|---|---|---|---|
| D | SSRF : `base_url` step-2 IBKR pris tel quel depuis XML | Haute | ✅ mergé PR #6 |
| B | `abs(commission)` swallows rebates positifs | Basse | ✅ mergé PR #7 |
| C | `sys.exit(1)` dans `ghost_find_account_id()` — non testable | Basse | ✅ mergé PR #8 |
| A | Corporate actions importées comme trades normaux | Moyenne | Ouvert — pas de PR |
| E | LSE/GBX : prix GBP importé tel quel → mismatch ×100 avec Yahoo GBp (qty/perf fantômes) | Haute | ✅ mergé #17 (`gbx_pence_conversion`) |
| F | Pas de mode `--dry-run` (preview des activités avant écriture) | Moyenne | Ouvert #20 |
| G | Activité créée **sans comment `IBKR#<tradeID>`** quand le symbole est **canonicalisé par Yahoo** (ex. `TAL.V`→`TAL.TO`) → re-duplication au sync suivant. (Les symboles non normalisés gardent bien le comment.) | Moyenne | Ouvert — à investiguer |

**Gotchas ops (hors code) :**
- `mapping.yaml` est monté en **bind-mount fichier** → l'éditer sur l'hôte ne se reflète pas (inode figé au `create`) : `docker restart` du container pour relire.
- Collision de ticker : mapper par **ISIN** (ex. IBKR `TAL`=PetroTal `CA71677J1012`≠TAL Education). Yahoo canonicalise `.V`→`.TO` pour PetroTal.

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
push main    → GitHub Actions build linux/amd64 + linux/arm64
             → push ghcr.io/flowcool/ghostfolio-ibkr-sync:latest
             → Portainer poll repo infra → redéploie le container

push staging → GitHub Actions build linux/amd64 + linux/arm64
             → push ghcr.io/flowcool/ghostfolio-ibkr-sync:staging
             → tester manuellement sur le NAS avant merge sur main
```

Pour switcher vers l'image du fork (PRs toutes mergées — à faire) :
- Changer `image:` dans `infra/repo/stacks/ugreen/ghostfolio/docker-compose.yml`
- Supprimer le volume workaround `ibkr_to_ghostfolio.py`

## 8. Références

- Fork : https://github.com/flowcool/ghostfolio-ibkr-sync
- Upstream : https://github.com/obol89/ghostfolio-ibkr-sync
- Ghostfolio API : `GET /api/v1/activities`, `POST /api/v1/import`, `GET /api/v1/account/{id}`
