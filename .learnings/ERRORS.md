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
