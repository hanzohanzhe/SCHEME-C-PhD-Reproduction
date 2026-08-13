# Git versioning and snapshot policy

Git is the authoritative version system for this archive and for future FORCE
snapshots.

- Every accepted state is a commit.
- A scientifically meaningful frozen state also receives an annotated tag.
- Development work is carried on a branch and merged only after its tests pass.
- Run outputs record the source commit and tag used to produce them.
- Historical tags are never moved or overwritten.
- ZIP files are optional offline backups, not the version identity.
- Large research data remains a separately versioned release asset whose hash
  and release tag are recorded by the code version.

The initial scientific tag for this repository is
`scheme-c-1000twh-2026-07-18_19`. Later corrections must receive a new tag and
must not rewrite that historical tag.
