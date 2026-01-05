## [2.1.4] - 2026-01-05

### 🐛 Bug Fixes

- *(ci)* Skip release-pr job on release commits
- *(publish)* Remove tokens from env when using OIDC trusted publishing

### 📚 Documentation

- Document CI limitation for release PRs created by GITHUB_TOKEN
- Update GitHub Actions workflow documentation

### ⚙️ Miscellaneous Tasks

- *(release)* Prepare v2.1.3 (#3)
## [2.1.3] - 2026-01-05

### 🐛 Bug Fixes

- *(ci)* Skip release-pr job on release commits

### 📚 Documentation

- Document CI limitation for release PRs created by GITHUB_TOKEN
- Update GitHub Actions workflow documentation
## [2.1.2] - 2026-01-05

### 🐛 Bug Fixes

- Improve PyPI token handling and GitHub release error messages
- *(ci)* Add dry-run: false to actually create PRs and releases
- *(action)* Add --execute flag for release-pr and release commands
- *(action)* Install git-cliff for changelog generation
- *(action)* Configure git identity for commits

### 📚 Documentation

- Clarify git-cliff is a required external binary
- Add required repository settings for GitHub Actions

### ⚙️ Miscellaneous Tasks

- *(release)* Prepare v2.1.1 (#1)
## [2.1.1] - 2026-01-05

### 🐛 Bug Fixes

- Improve PyPI token handling and GitHub release error messages
- *(ci)* Add dry-run: false to actually create PRs and releases
- *(action)* Add --execute flag for release-pr and release commands
- *(action)* Install git-cliff for changelog generation
- *(action)* Configure git identity for commits

### 📚 Documentation

- Clarify git-cliff is a required external binary
- Add required repository settings for GitHub Actions
## [2.1.0] - 2026-01-05

### 🚀 Features

- Implement changelog, security, hooks, and publishing features
## [2.0.1] - 2026-01-05

### 🐛 Bug Fixes

- *(config)* Move tag_prefix and changelog_path to correct sections

### ⚙️ Miscellaneous Tasks

- Update .gitignore with test artifacts
- Add allow_dirty config option