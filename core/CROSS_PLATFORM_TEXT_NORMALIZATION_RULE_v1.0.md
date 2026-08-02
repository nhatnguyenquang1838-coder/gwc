# Cross-Platform Text Normalization Rule v1.0

## Purpose

All governed repositories must produce identical tracked text bytes on Linux, macOS, Windows, local agent worktrees, GitHub Actions runners, and connector-materialized sessions.

## Canonical text format

Tracked text files use UTF-8 without BOM and LF (`\n`) line endings. CRLF (`\r\n`) and bare carriage returns (`\r`) are prohibited unless an explicit, reviewed `.gitattributes` exception exists.

Normalization must occur before SHA-256 calculation, scope-hash artifact generation, manifest generation, schema validation, package export, commit, push, or CI evidence capture.

## Required order

```text
write or generate file
-> normalize to UTF-8 and LF
-> validate line endings
-> calculate SHA-256
-> update dependent SHA pins
-> regenerate manifests and packages
-> validate exact bytes
-> commit
```

A file changed after hashing invalidates the hash and all dependent manifests or evidence.

## Repository controls

Every governed repository must contain:

- root `.gitattributes` with `* text=auto eol=lf` and explicit binary classifications;
- root `.editorconfig` with `charset = utf-8`, `end_of_line = lf`, and `insert_final_newline = true`;
- `tools/validate_line_endings.py`;
- CI that runs line-ending validation before instruction, SHA, schema, package, or governance validation.

`.editorconfig` controls editors. `.gitattributes` controls Git normalization. Neither replaces the other.

## Local-agent worktree configuration

Local agents must verify worktree-effective Git configuration:

```text
core.autocrlf=false
core.eol=lf
core.safecrlf=true
```

Agents may set these values at worktree scope when supported. They must not modify a developer's global Git configuration without explicit authority.

## Gate boundaries

Before G2, an agent may normalize only allowlisted task planning and governance artifacts in its isolated workspace. Repository-wide renormalization, staging, commit, push, or broad historical evidence rewrites remain prohibited.

After exact G2 authority, a one-time repository migration may run `git add --renormalize .` within approved scope. Broad normalization must be isolated from unrelated functional changes and reviewed for binary, executable-bit, semantic, and historical-evidence drift.

## Validator behavior

The validator must inspect tracked text files and reject:

- CRLF bytes;
- bare carriage returns;
- UTF-8 BOM unless explicitly allowlisted;
- invalid UTF-8 in files classified as text;
- missing final newline for governed text files;
- `.gitattributes` classifications inconsistent with the LF policy.

Binary files must not be decoded as text.

Required result codes:

```text
0 = PASS
1 = text normalization violation
2 = validator configuration or I/O error
```

## CI ordering

Line-ending validation runs first. A later validator result is not trustworthy evidence when normalization validation failed.

The LF and SHA parity suite must run on Ubuntu, macOS, and Windows and prove that the same commit produces identical canonical-policy hashes and package-manifest hashes.

## Python I/O

Validators and generators must specify encoding and newline behavior explicitly:

```python
path.read_text(encoding="utf-8")
path.write_text(content, encoding="utf-8", newline="\n")
```

Byte-bound hashes must use `read_bytes()`.

## SHA closure

```text
LF validator PASS
-> calculate file SHA-256
-> update active pins
-> regenerate manifests/packages
-> rerun LF validator
-> SHA parity PASS
```

Historical `.gwc/tasks/**` evidence must not be mass-updated to current hashes. Rebaseline only through a new evidence revision and required approval.

## Failure codes

- `LINE_ENDING_POLICY_MISSING`
- `GIT_ATTRIBUTES_INCOMPLETE`
- `EDITORCONFIG_MISSING`
- `CRLF_DETECTED`
- `BARE_CR_DETECTED`
- `UTF8_BOM_DETECTED`
- `INVALID_UTF8`
- `FINAL_NEWLINE_MISSING`
- `ATTRIBUTE_CLASSIFICATION_MISMATCH`
- `WORKTREE_GIT_EOL_MISCONFIGURED`
- `GENERATED_FILE_NOT_LF`
- `CROSS_OS_HASH_MISMATCH`
- `NORMALIZATION_SCOPE_DRIFT`
- `HASH_CALCULATED_BEFORE_NORMALIZATION`
- `LINE_ENDING_VALIDATION_NOT_RUN`

Any failure blocks SHA closure, commit, push, package publication, and G3 PASS.
