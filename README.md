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
  skills; the `best-in-class`, `coverage`, `recall` and `judge` agents
  `elucidate` spawns; a hook before every tool call that keeps the corpus
  behind `reqctl`, refuses any edit of a citation that `reqctl` did not make,
  shows the governing statement when an edit reaches cited lines, and refuses
  a commit or push to the default branch, a force push and a git command that
  discards uncommitted work; and one that gives each session reqctl's rules
  when it starts or compacts. It installs into any git repository, with or
  without a corpus.
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
  and `reqctl validate` checks the form. `reqctl lint` reports what `reqctl new`
  would refuse, writing nothing.
- An item's stamp is a digest of the fields that state it.
- An item is draft, approved, deprecated or superseded. Approval is the merge:
  only the default branch states what is approved, and `reqctl baseline` cuts
  and checks the manifest of it.
- A `settings.yml` in `requirements/` replaces values reqctl ships: review
  limits, challenge bounds, the elucidate agents' models and effort, the portal
  token's permissions, and whether `reqctl trace` reports code no citation
  covers. reqctl reads it as the default branch at `origin` carries it, so a
  change to it takes effect on merge.

## Working

1. **State.** Give `elucidate` an idea. It reads the repository's README for
   the field the software is in, reviews what best in class does there, and
   puts to the owner the practices the idea does not state. It proposes the
   practice that fits the project as each idea's default answer, drafts EARS
   statements, challenges them against the approved corpus through the
   `recall` and `judge` agents, puts to the owner from that challenge only a
   question naming a contradiction with an approved item, asks which proposals
   to mint, and opens a pull request that changes the corpus and nothing else.
2. **Read.** `reqctl context UID` prints an item, its links and the code that
   cites it. Never implement from a UID alone.
3. **Build and cite.** Write the smallest code that satisfies the statement,
   then `reqctl tag PATH --from N --to M --req UID`; `--name` cites a Python
   function, class or method, and a path alone cites a whole file. The
   citation pins the statement's stamp in the code, and the item records a
   digest of the lines it covers. A citation covers the code that decides a
   clause and every line that code names which no citation digest takes in; a
   Python citation's digest takes in each function, class and constant its
   lines name. `implement` carries steps 2 and 3.
4. **Check.** `reqctl compare` names every cited region the branch touches; read
   each against its statement. `reqctl trace` maps citations to the corpus:
   it reports a citation whose covered lines changed since it was pinned or
   that names a deprecated statement, warns of each approved statement nothing
   cites, and, where `settings.yml` asks, reports the lines no citation covers.
   `pre-pr` runs the gates before a code pull request.
5. **Re-pin.** A merged statement change leaves its citations stale. Read the
   code against the new statement, then `reqctl repin ID`, or `reqctl untag ID`
   where it no longer governs.

`reqctl list` names what the corpus holds; `reqctl export` prints what is
approved, or everything with `--all`. `reqctl --json` before any command prints
records in place of markdown.

## Adopting reqctl

In a repository whose default branch is `main`:

1. **CLI.** Install the wheel attached to the release the plugin is pinned to.
   Releases are tagged `reqctl--v<version>`:

   ```bash
   pip install https://github.com/threldhq/reqctl/releases/download/reqctl--v0.1.19/reqctl-0.1.19-py3-none-any.whl
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
     them. It applies the portal's steps -- new, revise, relate, unrelate,
     delete -- through reqctl, cuts and checks a baseline where a step changes
     something approved, and opens a pull request.
   - Both calls pass the two secrets, and `reqctl` as a full 40-character commit
     SHA. Each stops before reading a secret when `reqctl` is anything else or a
     pull request triggered the caller.
   - Run `reqctl portal` in a clone whose `origin` is the repository. It serves
     the page at `http://127.0.0.1:8374` and asks for a fine-grained token
     scoped to that repository: actions read and write, contents read, pull
     requests read. The page sends requests to GitHub's API and nowhere else.

## This repository

reqctl governs itself. Its corpus states what reqctl, the plugin and the
workflows do (`REQ`) and what the build that makes and checks them does
(`GUARD`). `.github/workflows/ci.yml` and `.github/workflows/corpus-gates.yml`
gate every pull request, and `python .github/verify.py` runs the steps they
would run for the tree. The repository holds no test and the corpus offers no
automated_test verification: code is verified by reading it against the
statement it cites. `.github/CODEOWNERS` puts the owner on every path: Claude
writes and opens pull requests, the owner reviews and merges. Every bug and
every request starts as a GitHub issue, and CI refuses a pull request whose body
names none. A push to `main` that first pins the plugin to a new version tags
the release and attaches the reqctl wheel to it.

Licensed under Apache-2.0; see `LICENSE.txt`.
