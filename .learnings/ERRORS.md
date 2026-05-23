# Errors

Command failures and integration errors.

---

## 2026-05-23 - PowerShell foreach pipeline parse error

**Command Context:** While inspecting local Codex cache directories, a one-line PowerShell command attempted to pipe directly after a `foreach` statement.

**Error:** `EmptyPipeElement` parser error.

**Resolution:** Wrap statement output in `& { ... } | ...` or assign results to a variable before piping.

**Status:** resolved

---

## [ERR-20260523-001] rg_access_denied

**Logged**: 2026-05-23T00:00:00+08:00
**Priority**: low
**Status**: pending
**Area**: infra

### Summary
`rg --files` failed with access denied in the Jijin workspace, so PowerShell native file listing was used as a fallback.

### Error
```text
程序“rg.exe”无法运行: 拒绝访问。
```

### Context
- Command attempted: `rg --files`
- Environment: PowerShell in `C:\Users\Halo\Documents\Jijin`

### Suggested Fix
Check whether the bundled `rg.exe` is blocked by Windows permissions or security software; use `Get-ChildItem` as a fallback when needed.

### Metadata
- Reproducible: unknown
- Related Files: none

---

## [ERR-20260523-002] pytest_script_import_path

**Logged**: 2026-05-23T00:00:00+08:00
**Priority**: low
**Status**: pending
**Area**: tests

### Summary
Running `pytest` directly from `backend` failed to import the local `app` package, while `python -m pytest` used the expected current-directory import path.

### Error
```text
ModuleNotFoundError: No module named 'app'
```

### Context
- Command attempted: `pytest`
- Working directory: `C:\Users\Halo\Documents\Jijin\backend`
- Working command: `python -m pytest`

### Suggested Fix
Use `python -m pytest` for backend verification, or add a pytest configuration that explicitly sets the Python path.

### Metadata
- Reproducible: yes
- Related Files: backend/tests/test_api.py, backend/tests/test_strategy.py

---

## [ERR-20260523-003] vite_build_sandbox_access

**Logged**: 2026-05-23T00:00:00+08:00
**Priority**: low
**Status**: pending
**Area**: frontend

### Summary
`npm run build` failed inside the sandbox because Vite/esbuild could not read parent directories or resolve `vite.config.ts`; rerunning with approved escalation succeeded.

### Error
```text
Cannot read directory "../../..": Access is denied.
Could not resolve "C:\\Users\\Halo\\Documents\\Jijin\\frontend\\vite.config.ts"
```

### Context
- Command attempted: `npm run build`
- Working directory: `C:\Users\Halo\Documents\Jijin\frontend`

### Suggested Fix
Use the approved `npm run build` escalation rule when sandboxed builds hit Windows access-denied errors.

### Metadata
- Reproducible: unknown
- Related Files: frontend/vite.config.ts

---
