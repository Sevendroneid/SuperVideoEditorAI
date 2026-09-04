# SuperVideoEditorAI

AI Director / AI Visual Storyteller prototype.

## Prototype goal

Turn a small collection of raw video clips into a coherent short visual story by:

1. inspecting clips,
2. extracting measurable shot information,
3. ranking candidate shots,
4. constructing a story sequence,
5. rendering the sequence with FFmpeg.

This repository intentionally starts as a small proof-of-concept. No paid AI API is required for the first local prototype.

## Current status

**Phase 0 — architecture and prototype skeleton.**

The next implementation milestone is a local pipeline that accepts sample clips and produces a machine-readable shot report and deterministic rendered sequence.

## Design principles

- No assumptions about footage: decisions must be traceable to extracted evidence.
- AI reasoning and deterministic video processing remain separate.
- Timeline data is structured and reproducible.
- A beautiful shot is not automatically the best story shot.
- The prototype must be tested with real footage before adding paid infrastructure.

## Proposed pipeline

```text
Raw clips
   -> technical inspection
   -> shot/segment detection
   -> visual/audio evidence
   -> candidate ranking
   -> story sequence
   -> timeline JSON
   -> FFmpeg render
   -> output MP4
```

## Cost target

Prototype target: **Rp0** using local/open-source components and free hosting/development tiers where applicable. Any service that introduces a charge must be explicitly verified before use.

## Verification rule

Do not claim a feature works until it has been executed and its output verified.
