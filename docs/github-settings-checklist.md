# Checklist des réglages GitHub

Réglages qui ne vivent pas dans les fichiers du dépôt : à vérifier à la main
dans l'interface, environ 10 minutes. À refaire après tout changement de
propriétaire, d'organisation ou de règle. Cochez ce qui est déjà en place.

Chemin général : dépôt > **Settings**.

## 1. Releases et tags (priorité haute)

- [ ] **Settings > General > Releases** : activer *Enable release immutability*.
      Une release publiée ne peut plus être modifiée, ni son tag déplacé ou
      supprimé. Attention : on ne pourra plus corriger le texte d'une release
      après publication, donc relire avant de publier (voir `docs/releasing.md`).
- [ ] **Settings > Rules > Rulesets > New ruleset > New tag ruleset** :
      cible `v*`, règles *Restrict creations*, *Restrict updates*,
      *Restrict deletions*, seul le propriétaire du dépôt peut contourner.
      Cela complète le contrôle de forme `vX.Y.Z` du workflow de publication.

## 2. Branche `main`

- [ ] **Rulesets** : une règle sur `main` avec *Require a pull request before
      merging*, *Block force pushes*, *Restrict deletions*.
- [ ] *Require status checks* : `test`, `dependency-audit`,
      `container-check (amd64)`, `container-check (arm64)`, `analyze` (CodeQL),
      `dependency-review`. **Ne pas** y mettre `label` : il est consultatif.
- [ ] **General > Pull Requests** : seul *Allow merge commits* est coché
      (squash et rebase décochés), *Automatically delete head branches* coché.

## 3. Sécurité

- [ ] **Settings > Advanced Security** (ou *Code security*) : *Dependency graph*,
      *Dependabot alerts*, *Dependabot security updates* activés.
- [ ] *Secret scanning* et *Push protection* activés.
- [ ] **Security > Private vulnerability reporting** activé (la politique
      `SECURITY.md` renvoie vers un signalement privé).

## 4. GitHub Actions

- [ ] **Settings > Actions > General > Actions permissions** : *Allow owner, and
      select non-owner actions*, avec les actions épinglées autorisées par SHA.
- [ ] **Workflow permissions** : *Read repository contents and packages
      permissions*. Chaque workflow demande ses droits d'écriture lui-même.
- [ ] *Allow GitHub Actions to create and approve pull requests* : décoché.
- [ ] **Fork pull request workflows** : *Require approval for all external
      contributors*.

## 5. Image conteneur (GHCR)

- [ ] **Profil ou organisation > Packages > ghostfolio-ibkr-sync > Package
      settings** : paquet lié au dépôt, visibilité voulue (public pour un
      `docker pull` sans connexion).
- [ ] Ne pas supprimer d'anciennes versions d'image : elles servent au retour
      arrière. `docs/releasing.md` demande de noter le digest précédent.

## 6. Étiquettes (cosmétique)

- [ ] **Issues > Labels** : donner couleur et description aux étiquettes
      `breaking-change` (rouge), `compat` (orange), `feature`, `fix`,
      `documentation`, `maintenance`. Elles ont été créées sans couleur.
