# ADR-0001 — Architecture Decision Records'ı tutmaya başla

**Status:** Accepted
**Date:** 2026-05-01
**Owner:** The Abi
**Related:** [`/docs/10_Production_Pivot_Spec.md`](../10_Production_Pivot_Spec.md)

## Context

RafRaf v0.1'de mimari kararlar tek bir master plan doc'unda gömülü. v1'e pivot sırasında (production pivot) hangi kararın **neden** alındığı tarihsel olarak takip edilemiyor — özellikle yeni bir Claude session veya developer kod'a ilk baktığında "neden FastAPI değil Go bridge?" gibi soruların cevabı kaybolmuş oluyor.

## Decision

`docs/adr/` dizininde **Markdown Architecture Decision Records** tutulacak. Format: Michael Nygard ADR şablonu, kısa.

Her ADR şu bölümleri içerir:
- **Status**: Proposed / Accepted / Deprecated / Superseded by ADR-XXXX
- **Date**: YYYY-MM-DD
- **Owner**: karar sahibi
- **Related**: ilgili doc'lar/ADR'ler
- **Context**: neden karar gerekti, hangi soru soruldu
- **Decision**: ne karar verildi (tek-iki cümle)
- **Consequences**: pozitif + negatif sonuçlar, ileride hangi değişiklikler kolaylaşır/zorlaşır
- **Alternatives considered**: değerlendirilen ama reddedilen alternatifler

Numaralandırma 4 haneli, sıralı: `0001-`, `0002-`, ...

## Consequences

**Pozitif:**
- Yeni session karar geçmişini hızlıca okur (5 dk'lık bir doc, 50 sayfa master plan'a göre)
- "Neden X?" sorularına tek noktadan cevap
- Deprecate edilen kararlar Superseded by referansıyla zincirlenir

**Negatif:**
- Yeni karar alındığında ADR yazma disiplini gerek (yoksa doc lake'e döner)
- Master plan + ADR ikisi senkron tutulmalı (ADR daha sade, master detaylı)

## Alternatives considered

- **A)** Sadece master plan içinde "Decision Log" bölümü: birleşik ama uzun; yeni okuyan tüm doc'u tarayacak.
- **B)** GitHub Discussions: arama zayıf, repo'da değil.
- **C) (Seçildi)** ADR Markdown — repo'da, kısa, tarihsel.
