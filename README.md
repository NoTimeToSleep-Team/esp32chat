# Local Chat Server Project

This repository contains the staged implementation of a local distributed chat server built around Raspberry Pi 5, internal service controllers, and external hardware clients.

## Current State

- Work is in early foundation stage (`v0.01.01`).
- The repository currently defines structure, rules, and planning artifacts.
- Server and firmware implementation will be added in next staged versions.

## Repository Layout

- `docs/` - architecture and project documentation.
- `contracts/` - protocol and sync contracts between server and firmware.
- `server/` - Raspberry Pi backend, web portal, data services, and admin APIs.
- `firmware/` - device firmware and client applications.

## Core Principles

- Build in small, verifiable versions.
- Keep hardware roles realistic.
- Use defensive security only.
- Do not claim tests or hardware checks that were not actually executed.

## Context Files

- `SESSION_CONTEXT.md` - permanent project/session rules.
- `STAGE_CONTEXT.md` - current stage context.
- `SUBSTAGE_CONTEXT.md` - active substage context.
- `PLAN.md` - full roadmap and version transitions.
