# Phase 1 — System Baseline
Date: 2026-09-28 Asia/Bangkok
Status: PASS for baseline observation; no production integration installed.

## Host
- Windows: Microsoft Windows NT 10.0.26200.0
- PowerShell: 5.1.26100.9549
- C: NTFS, 510,481,395,712 bytes total; 188,885,467,136 bytes free
- D: FAT32, 7,972,323,328 bytes total; ~7,971,975,168 bytes free
- Host health for C/D volumes: Healthy

## Docker / WSL
- Docker Engine: 29.8.0
- Docker Compose: v5.5.1
- Docker Desktop backend: active
- WSL default distro: Ubuntu-26.04
- WSL default version: 2
- Ubuntu-26.04: Running
- docker-desktop: Running

## Docker workload observed
- n8n: running on TCP 5678
- Woodpecker server: running on TCP 8000
- Woodpecker agent: running
- two Cloudflare containers: running
- Forgejo: running
- PostgreSQL is not running as a host Windows service

## Resource conflicts
- TCP 8000 is already occupied by Woodpecker Server.
- Candidate BrightBean local bind ports 18100-18102 were tested free.
## Hermes
- Hermes version: 0.21.5+3724.g14c4b62
- Upstream revision: 14c4b62e
- Install path: C:\Users\chara\AppData\Local\hermes\hermes-agent
- Install method: git
- Python: 3.14.7
- Gateway: RUNNING via default-profile multiplexer
- Existing shared listener: 127.0.0.1:8644
- Existing Line callback route is present
- Hermes reports 7 commits available via update; no update was performed in Phase 1.

## Hermes MCP baseline
Configured/visible MCP servers include Buffer, Cloudflare, GitHub, n8n, Playwright and other existing services.
No BrightBean MCP is currently configured.
Workspace C:\Workspace\super-creator-os\.mcp.json currently declares only the local scos-video MCP.

## Workspace
- Project path: C:\Workspace\super-creator-os
- Git branch: main
- HEAD: 864ef5c7c9f049b327cc257fb561ae7f01b6a348
- Working tree is substantially dirty with pre-existing modifications/deletions/untracked files.
- No cleanup or unrelated git changes were performed.

## Phase 1 conclusion
The required execution environment exists. Main known constraints are the occupied TCP 8000,
the already-dirty workspace, and the need to keep BrightBean isolated from existing services.
