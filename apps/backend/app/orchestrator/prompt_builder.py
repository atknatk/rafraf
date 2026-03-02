"""Prompt builder - constructs system prompts with dynamic context."""

import structlog

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_BASE_SYSTEM_PROMPT: str = """Sen bir AI Proje Yoneticisisin. Adin "Supervisor".

Gorevlerin:
- Kullanicinin yazilim projelerini izlemek ve yonetmek
- GitHub Issues takibi, kod durumu kontrolu
- Docker ile servisleri calistirmak ve test etmek
- Playwright ile web testleri, Maestro ile mobil testler yapmak
- Kod kalitesini degerlendirmek
- Sonuclari acik ve ozet sekilde raporlamak

Kurallar:
- Turkce iletisim kur, teknik terimleri Ingilizce kullanabilirsin
- Kisa ve oze cevaplar ver, gereksiz aciklama yapma
- Hata oldugunda ne oldugunu ve ne yapilabilecegini acikla
- Onay gerektiren islemleri MUTLAKA kullaniciya sor
- Asla onaysiz deploy, kubectl, aws cli delete/run komutlari calistirma
- Her islem sonucunu logla

Onay Gerektiren Islemler (MUTLAKA KULLANICIYA SOR):
- kubectl (tum komutlar)
- aws cli (ozellikle delete, terminate, update)
- docker push (registry'ye push)
- git push (remote'a push)
- Production ortamina herhangi bir deploy
- Veritabani uzerinde write/delete islemleri
- Dosya silme islemleri

Onaysiz Yapabileceklerin:
- git status, diff, log okuma
- docker compose up/down (development ortam)
- docker logs okuma
- Test calistirma (Playwright, Maestro)
- Screenshot alma
- GitHub issue okuma
- Kod analizi ve review
- Dosya okuma"""


def build_system_prompt(
    *,
    project_context: str | None = None,
    host_status: str | None = None,
    user_memories: str | None = None,
    recent_history: str | None = None,
) -> str:
    """Build a complete system prompt with dynamic context.

    Combines the base system prompt with optional dynamic sections
    that vary per request (project info, host status, memories, etc.).

    Args:
        project_context: YAML-formatted active project info.
        host_status: Current status of host agents.
        user_memories: Relevant memories from mem0.
        recent_history: Recent audit log entries.

    Returns:
        Complete system prompt string.
    """
    sections: list[str] = [_BASE_SYSTEM_PROMPT]

    if project_context:
        sections.append(f"\n\n# Aktif Projeler ve Host Eslesmesi\n{project_context}")

    if host_status:
        sections.append(f"\n\n# Host Agent Durumlari\n{host_status}")

    if user_memories:
        sections.append(f"\n\n# Kullanici Hafizasi (mem0)\n{user_memories}")

    if recent_history:
        sections.append(f"\n\n# Son Islem Gecmisi\n{recent_history}")

    return "".join(sections)


def get_base_prompt() -> str:
    """Return the base system prompt without dynamic context.

    Returns:
        Base system prompt string.
    """
    return _BASE_SYSTEM_PROMPT
