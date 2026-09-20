# Provenance

Files were copied from the paper's working tree. Original paths are relative to
`papers/paper_mesas/` in the `rv-3-layer` research repository.

| Here | Original |
|---|---|
| `harness/**` | `paper3_swarm/harness/**` |
| `harness/HARNESS_NOTES.md` | `paper3_swarm/harness/README.md` |
| `console/**` | `paper3_swarm/console/**` |

Written for this repository, not copied: `README.md`, `run_all.sh`,
`CITATION.cff`, `LICENSE`, `PROVENANCE.md`, `.gitignore`.

## The one file modified in the move

`harness/LINUX_VM.md`, line 85. The original contained a plaintext cloud-init
password for a throwaway local Ubuntu VM. The value was replaced with
`CHANGEME`. Nothing else in this repository was edited.

## Deliberately excluded

- `paper3_swarm/harness/.e2e-venv/` (122 MB) — a checked-in Python virtualenv.
  It is a build artefact, not source, and it should not be redistributed.
- `__pycache__/` directories and `.DS_Store` files.
- The LaTeX sources, PDFs, figures and submission zips in `paper3_swarm/` —
  paper material, not code.

## Secret scan

The copied tree was scanned for API keys, private keys and credential-shaped
strings. Findings:

- No API keys anywhere, in source or in the archived `.jsonl` model runs.
- `llm_loop.py` and the `exp_*.py` drivers read credentials from the environment
  only: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY` /
  `GOOGLE_API_KEY`, `DEEPSEEK_API_KEY`. No defaults, no fallbacks to a literal.
- The single plaintext VM password described above, now redacted.
- `NOPASSWD:ALL` occurrences in `LINUX_VM.md` and `sitl_mission/sitl_bootstrap.sh`
  are sudoers configuration for a disposable build VM, not credentials.

## Sharing with the other MESAS repositories

None. Every `.py` and `.sh` file in this repository was compared by content hash
against the other two MESAS code trees (`paper1_dtloop/experiments/` and
`agent-rv-impl/`). There are zero shared files.
