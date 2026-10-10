# reqctl

> The corpus is the only approved statement of what reqctl does. This page
> orients and approves nothing; `reqctl --help` is the index.

reqctl is requirements management for software built with AI coding agents.
Requirements live in the repository as a corpus of stamped items, are approved
by the merge of a pull request, and are traced to the code that satisfies them.
Each citation in the code pins the stamp of the statement as it was last read,
so when a statement changes every citation of it goes stale, and CI refuses the
code until each is read against the statement that now stands and re-pinned.

## What ships

- **`reqctl`** -- the CLI, and the only way a corpus is read or written. Python
  3.13 or later.
- **The Claude Code plugin** -- the `elucidate`, `implement` and `pre-pr`
  skills; the `best-in-class` and `coverage` agents; a hook before every tool
  call that keeps the corpus behind `reqctl`, and one that gives each session
  reqctl's rules when it starts or compacts.
- **Reusable workflows** -- `.github/workflows/corpus-gates.yml` refuses a pull
  request that fails a corpus gate; `.github/workflows/corpus-view.yml`
  publishes the corpus for the portal; `.github/workflows/corpus-write.yml`
  applies a change made in the portal and opens a pull request.
- **The portal** -- `reqctl portal` serves a local page that reads the corpus
  and proposes changes to it.

## The corpus

`requirements/` holds one YAML file per item:

| Kind | UID | States |
| --- | --- | --- |
| requirement | `REQ-` and eight digits | what the product shall do |
| guard | `GUARD-` and eight digits | what the build shall do |
| parameter | its name | a value statements reference |
| term | its name | a word statements link wherever they use it |
| data | its name | a set of entries statements reference |

- Requirements and guards are EARS statements -- The, When, While, If, Where --
  and `reqctl validate` checks the form.
- An item's stamp is a digest of the fields that state it.
- An item is draft, approved, deprecated or superseded. Approval is the merge:
  only the default branch states what is approved, and `reqctl baseline` cuts
  and checks the manifest of it.
- A `settings.yml` in `requirements/` replaces values reqctl ships: review
  limits, challenge bounds, the elucidate agents' models and effort, the portal
  token's permissions.

## Working

1. **State.** Give `elucidate` an idea. It reviews what best in class does,
   drafts EARS statements, challenges them against the approved corpus, and
   opens a pull request that changes the corpus and nothing else.
2. **Read.** `reqctl context UID` prints an item, its links and the code that
   cites it. Never implement from a UID alone.
3. **Build and cite.** Write the smallest code that satisfies the statement,
   then `reqctl tag PATH --from N --to M --req UID`. `implement` carries steps 2
   and 3.
4. **Check.** `reqctl compare` names every cited region the branch touches; read
   each against its statement. `reqctl trace` maps citations to the corpus.
   `pre-pr` runs the gates before a code pull request.
5. **Re-pin.** A merged statement change leaves its citations stale. Read the
   code against the new statement, then `reqctl repin ID`, or `reqctl untag ID`
   where it no longer governs.

`reqctl list` names what the corpus holds; `reqctl export` prints it.

## Adopting reqctl

In a repository whose default branch is `main`:

1. **CLI.** Install the wheel attached to the release the plugin is pinned to.
   Releases are tagged `reqctl--v<version>`:

   ```bash
   pip install https://github.com/threldhq/reqctl/releases/download/reqctl--v0.1.8/reqctl-0.1.8-py3-none-any.whl
   ```

2. **Plugin.** With `--scope project` both are declared in the repository rather
   than for one user:

   ```bash
   claude plugin marketplace add threldhq/reqctl --scope project
   claude plugin install reqctl@reqctl --scope project
   ```

   No corpus is needed first: the first `reqctl new` creates `requirements/`.

3. **Gates.** From a workflow run on `pull_request`, call this repository's
   `.github/workflows/corpus-gates.yml` at a release's commit SHA, passing that
   SHA as input `reqctl`. It refuses a pull request that fails baseline_match,
   baseline_numbering, corpus_validity, stamp_admission, taxonomy, traceability
   or travel_alone.

4. **Portal.**
   - A GitHub App installed on the repository with read and write access to
     contents and pull requests, its client ID and private key stored as
     secrets `CORPUS_APP_CLIENT_ID` and `CORPUS_APP_PRIVATE_KEY`.
   - A workflow run on push to `main` that calls
     `.github/workflows/corpus-view.yml`. It publishes the corpus to the
     `corpus-view` branch, where the portal reads it.
   - A workflow named `corpus-write.yml`, run on `workflow_dispatch` with inputs
     `change` and `title`, that calls `.github/workflows/corpus-write.yml` with
     them. It applies the portal's steps through reqctl and opens a pull
     request.
   - Both calls pass the two secrets, and `reqctl` as a full 40-character commit
     SHA. Each stops before reading a secret when `reqctl` is anything else or a
     pull request triggered the caller.
   - Run `reqctl portal` in a clone whose `origin` is the repository. It serves
     the page at `http://127.0.0.1:8374` and asks for a fine-grained token
     scoped to that repository: actions read and write, contents read, pull
     requests read.

## This repository

reqctl governs itself. Its corpus states what reqctl, the plugin and the
workflows do (`REQ`) and what the build that makes and checks them does
(`GUARD`). `.github/workflows/ci.yml` and `.github/workflows/corpus-gates.yml`
gate every pull request, and `python .github/verify.py` runs the steps they
would run for the tree. `.github/CODEOWNERS` puts the owner on every path: Claude
writes and opens pull requests, the owner reviews and merges.

Licensed under Apache-2.0; see `LICENSE.txt`.
