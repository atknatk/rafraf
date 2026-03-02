# Feature: Shell Runner (Whitelist/Blacklist Security)

**Issue**: #16
**Faz**: F2
**Katmanlar**: agent
**Pipeline**: full
**Tarih**: 2026-03-02

## Ozet

Guvenli shell komut calistirici. Host Agent'in backend'ten gelen shell komutlarini
guvenli bir sekilde calistirmasini saglar. Whitelist/blacklist mekanizmasi ile sadece
izin verilen komutlar calistirilir, tehlikeli komutlar engellenir ve onay gerektiren
komutlar backend'e bildirilir. Injection korunmasi, timeout handling ve output capture
ozellikleri icerdir.

## Degisecek Dosyalar

### Agent (`apps/agent/`)
| Dosya | Islem | Aciklama |
|-------|-------|----------|
| `agent/security/__init__.py` | MODIFY | Export'lari guncelle |
| `agent/security/whitelist.py` | CREATE | Izin verilen komut pattern'leri |
| `agent/security/blacklist.py` | CREATE | Yasakli komut pattern'leri |
| `agent/security/sanitizer.py` | CREATE | Shell metacharacter filtreleme |
| `agent/runners/shell_runner.py` | CREATE | Shell komutu calistirici |
| `agent/runners/__init__.py` | MODIFY | ShellRunner export'u ekle |

## API Endpoints

Bu feature yeni REST veya WebSocket endpoint'i gerektirmez. Shell runner,
mevcut `agent_command` WebSocket mesaj akisi uzerinden tetiklenir.

Mevcut akis:
- Backend -> Agent: `agent_command` mesaji (`tool: "shell"`, `action: "run_command"`)
- Agent -> Backend: `command_result` mesaji (stdout, stderr, return_code)

## Data Model

### Pydantic Models

```python
from pydantic import BaseModel, ConfigDict


class ShellCommandResult(BaseModel):
    """Shell komut sonucu - frozen domain model."""
    model_config = ConfigDict(frozen=True)

    success: bool
    output: str
    error: str | None = None
    return_code: int | None = None
    timed_out: bool = False
    blocked_reason: str | None = None


class SecurityCheckResult(BaseModel):
    """Guvenlik kontrol sonucu - frozen domain model."""
    model_config = ConfigDict(frozen=True)

    allowed: bool
    reason: str
    check_type: str  # "whitelist", "blacklist", "approval_required", "injection"
```

## Business Rules

1. **Blacklist Onceligi**: Blacklist kontrolu her zaman ilk yapilir. Blacklist'e eslesen komut ASLA calistirilmaz.
2. **Approval Kontrolu**: Blacklist'ten gecen komut, approval pattern'lerine eslesiyorsa "ONAY_GEREKLI" hatasi doner.
3. **Whitelist Zorunlulugu**: Blacklist ve approval'dan gecen komut whitelist'te OLMALIDIR. Whitelist'te olmayan komut calistirilmaz.
4. **Injection Korunmasi**: Shell metacharacter'leri (`;`, `|`, `&&`, `` ` ``, `$()`, vb.) filtrelenir. Eger komut metacharacter iceriyorsa calistirilmaz.
5. **Timeout**: Maksimum 5 dakika (300 saniye). Varsayilan 60 saniye.
6. **Output Siniri**: stdout max 5000 karakter, stderr max 2000 karakter.
7. **Working Directory**: Komut belirtilen cwd icerisinde calistirilir. cwd verilmezse mevcut dizin kullanilir.
8. **Subprocess Izolasyonu**: `shell=False` (create_subprocess_exec) tercih edilir, ancak bazi komutlar icin `shell=True` (create_subprocess_shell) kullanilabilir — bu durumda injection kontrolu KRITIK.

## Security Patterns

### Whitelist (docs/08 referans)
```python
WHITELIST_PATTERNS = [
    r"^git\s+(status|log|diff|branch|show|remote|tag)",
    r"^ls\b", r"^cat\b", r"^head\b", r"^tail\b", r"^grep\b", r"^find\b", r"^wc\b",
    r"^docker\s+(ps|logs|stats|inspect|images)",
    r"^npm\s+(test|run\s+lint|run\s+build|run\s+dev|list)",
    r"^npx\b",
    r"^python\s+-m\s+(pytest|pylint|black|mypy)",
    r"^node\b",
    r"^curl\s+.*--request\s+GET|^curl\s+-s",
    r"^df\b", r"^du\b", r"^free\b", r"^top\s+-bn1", r"^ps\b",
    r"^which\b", r"^whoami\b", r"^uname\b", r"^hostname\b",
]
```

### Blacklist (docs/08 referans)
```python
BLACKLIST_PATTERNS = [
    r"rm\s+-rf\s+/",
    r"mkfs\b",
    r"dd\s+if=/dev",
    r":\(\)\s*\{",              # Fork bomb
    r">\s*/dev/sd",
    r"shutdown\b", r"reboot\b", r"halt\b",
    r"passwd\b",
    r"sudo\s+rm",
]
```

### Approval Required (docs/07 referans)
```python
APPROVAL_PATTERNS = [
    r"^kubectl\b",
    r"^aws\b",
    r"^docker\s+push",
    r"^git\s+push",
    r"^npm\s+publish",
    r"^rm\b",
    r"^chmod\b", r"^chown\b",
    r"^pip\s+install",
    r"^sudo\b",
]
```

### Injection Patterns
```python
INJECTION_PATTERNS = [
    r"[;|&`]",           # Komut zincirleme
    r"\$\(",             # Command substitution
    r"\$\{",             # Variable expansion
    r">\s*>",            # Output redirection append
    r"<\(",              # Process substitution
]
```

## Test Requirements

### Agent
- [ ] Unit test: whitelist pattern eslesmesi (pozitif + negatif)
- [ ] Unit test: blacklist pattern eslesmesi (pozitif + negatif)
- [ ] Unit test: approval pattern eslesmesi
- [ ] Unit test: injection pattern tespiti
- [ ] Unit test: sanitizer metacharacter filtreleme
- [ ] Unit test: shell_runner.execute() happy path
- [ ] Unit test: shell_runner.execute() timeout handling
- [ ] Unit test: shell_runner.execute() blacklisted komut
- [ ] Unit test: shell_runner.execute() whitelist'te olmayan komut
- [ ] Unit test: shell_runner.execute() approval gerektiren komut
- [ ] Integration test: gercek subprocess calistirma (ls, echo, git status)
- [ ] Integration test: timeout senaryosu (sleep komutu ile)

## Acceptance Criteria

- [ ] Async subprocess ile komut calistirma
- [ ] Whitelist mekanizmasi (izin verilen komutlar)
- [ ] Blacklist mekanizmasi (yasakli komutlar/pattern'ler)
- [ ] Approval mekanizmasi (onay gerektiren komutlar)
- [ ] Timeout handling (max 5dk, varsayilan 60sn)
- [ ] Output capture (stdout + stderr, karakter limiti ile)
- [ ] Working directory izolasyonu
- [ ] Injection korunmasi (shell metacharacter filtreleme)
- [ ] Unit + integration testler yazildi
- [ ] Coverage >= 80%
