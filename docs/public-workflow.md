# Public repository workflow

The project uses two deliberately unrelated histories:

* `master` is the private historical development branch. It is never pushed
  to GitHub and must never be merged or rebased with `public-main`.
* `public-main` tracks `public/main` and contains only the public repository's
  history. Public maintenance commits are made here.

The repository has a `public` remote and a local push guard. Do not remove the
guard or rely on an implicit push destination. Every public mutation must name
the remote and exact refspec.

## Normal maintenance

1. Keep private development on `master`.
2. Prepare a reviewed, clean snapshot ref without merging the histories.
3. Switch to `public-main` and fetch `public/main`.
4. Preview the snapshot:

   ```powershell
   .\packaging\Publish-PublicSnapshot.ps1 `
     -SourceRef <prepared-snapshot-ref> `
     -DestinationRef main `
     -DestinationRepository https://github.com/wwalsh/scrcpy-launcher.git `
     -DryRun
   ```

5. Review the exact commit and push operation. A real operation requires
   `-Publish`; the script never uses force push.

## Dependabot changes

Dependabot opens changes directly against public `main`. Review and merge them
on GitHub, then run `git fetch public main` and fast-forward only the local
`public-main` tracking branch with `git switch public-main; git pull --ff-only`.
Do not copy those commits into `master` or merge the two histories.

## Release snapshot preparation

Keep the application version and release tag unchanged until the release is
actually being prepared. A source tag must match `src/version.py`; the script
rejects mismatches and refuses to alter an existing remote tag. For an existing
release such as `v0.7.2`, use a dry run only and verify that the remote tag is
unchanged.

## Public main and release tag pushes

The publisher creates a commit from tracked Git content in a temporary clone
of the public destination, preserving the public history. It excludes ignored
configuration, logs, reports, build output, caches, virtual environments, and
other generated files. Use `-Publish` only after reviewing its preview.

Release tags are a separate operation after the public snapshot commit has
landed. Verify the tag and version, then push the exact tag ref explicitly:

```powershell
git push public refs/tags/<release-tag>:refs/tags/<release-tag>
```

Never move or recreate an existing tag, and never use `--force`.

## Release artifacts

Build and verify installer/portable artifacts separately using the documented
packaging lifecycle. Publish artifact files and checksums through the release
workflow only after source and tag verification. Artifact publication is not a
source-history push and must not be used to publish local configuration or
build directories.
## Cloudflare Pages deployment

The public repository deploys the dependency-free `site/` directory to the
`scrcpy-launcher` Cloudflare Pages project from public `main`. The project uses
no build command, has no environment variables, and publishes to the generated
`pages.dev` hostname plus the configured custom domains. Keep website changes
on `public-main`, preview them locally, run the site tests, and synchronize them
with `Publish-PublicSnapshot.ps1`; a successful public-main update should then
appear as an automatic Pages deployment. Do not change DNS or custom domains
outside the approved Cloudflare configuration.

