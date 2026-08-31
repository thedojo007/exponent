# Jarvis Next Steps

Fully rewritten from scratch every run, not appended to --
nothing here is permanent, don't build on top of it by hand.

_125 tasks scanned (Build Log + Components)._

## Today's Top 3 (suggestion only -- nothing written to ClickUp)

1. **Threshold Theo: live test (3-meeting) pending before Build Log entry** — Closest to shipping. This is explicitly mid-validation: the work is done and only the live test stands between it and a closed Build Log entry. Nothing else on the list is this close to done.

2. **Automate z: syncs** — Closes an open loop. The root cause is already diagnosed (Z: is office-LAN-only, QuickConnect misconfiguration, not a code bug), and the fix is a known, bounded action: reconfigure the Synology Drive Client to point at the QuickConnect address. This is also the small, single-sitting win — it's a config change, not a build, so it satisfies the constraint without needing to stretch either of the other two picks to fit.

3. **Session-to-Task pipeline (upgrade jarvis_session_sync.py)** — Unblocks other work. Several open items (Daily reconciliation agent, Next Steps completion-tracking, Weekly completed tasks as Jarvis input) all depend on session output being structured rather than raw text. Upgrading this script is the foundational piece those downstream tasks need before they're even well-specified, so fixing it first has the widest downstream effect on the rest of the backlog.

## Open Tasks by Context (51 open, 74 closed hidden)

### Work-Automation
- Bonding process automation
- 예산신청서 automation
- multi-sheet redistribution routing
- photo-evidence matching (사진대지 tab automation)
- 카드 소지자/직급/new projects as Claude input
- Explore Google Apps Script for the workflow
- Draft PRD for skill receipt extractor
- Extend project_lookup.py to company-wide registry
- ERP-Groupware evidence bridge
- attempt to make a perplexity, that will use csv and turn it into a quickbook journal file
- Have AI make a something something that turns 일반 카드 명세서 into a 지출결의서 form
- corporate-purchase-filing (ClickUp Skill)
- add_purchase.py
- 자금일보 학습 규칙 (Claude Desktop Skill)

### Personal
- Next Steps completion-tracking
- Claude API sessions (Stage 3+)
- Weekly completed tasks as Jarvis input
- Daily reconciliation agent
- Session-to-Task pipeline (upgrade jarvis_session_sync.py)
- Perplexity auto-warnings concept
- Living document pattern for AI outcomes
- Doc page restructuring
- Outstanding List redesign as backlog
- Sprint list automation
- Ops Odin auto-enhancement
- Cursor: build project from repository
- SOP habit (recurring reminder on Odin's cadence)
- Phone notes capture improvements
- Create calendar event for Jarvis runs
- Ops Odin override gap
- Notification reliability (Gmail SMTP digest)
- Recon: multi-user invocation
- Recon: internal-search-first
- Notes Inbox: multi-batch validation
- Jarvis self-directed stage
- Auto task-release agent (read-only flagging)
- Jarvis 4-stage architecture
- automate all manually laborious yet automatable goals

### 15%-Career
- Set up recurring job alerts
- Sign up for all Section: AI webinars

### (unset)
- Standing end-session protocol for task closure signal — scripting deferred
- Threshold Theo: live test (3-meeting) pending before Build Log entry
- Design seamless LinkedIn-Claude-ClickUp integration
- Build Claude/Perplexity engine to flag and update problematic QuickBooks entries
- Add automatic three-task recommendations to Claude
- Automate z: syncs
- Use full-sprint analysis in Evening Thunder
- Build Claude skill for job application tracker
- Build Claude skill for corporate purchase filing
- Build Claude skill for Kumyoung daily cash report
- make it so I have one.....
