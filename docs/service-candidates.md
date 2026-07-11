# Service Candidates

This document tracks possible OpenDock service additions and category ideas.

OpenDock should prefer services that are useful soon after launch, have official or stable Docker support, and can be configured with a small number of clear environment values. Service-specific operational tools are still allowed, but the default experience should stay close to install-and-use.

Another useful selection lens is commercial replacement value: pick categories where people commonly pay for a SaaS product, then offer a good open-source home-server alternative. This makes the value of OpenDock easy to feel: run it at home, keep your data, and reduce recurring subscriptions.

## Current Groups

```text
publishing: wordpress mastodon
automation: n8n
cloud: nextcloud
media: immich jellyfin
monitoring: uptime-kuma
communication: mattermost
```

## Strong Candidates

### communication

Communication is the groupware category most directly comparable to Slack, Microsoft Teams, Discord, or Google Chat. These services are useful for families, clubs, small teams, and project groups, not just companies.

Current group:

```text
communication: mattermost
```

#### Mattermost

Mattermost is a self-hosted team chat platform with channels, direct messages, file sharing, integrations, and a Slack-like mental model.

Commercial replacement angle:

- Alternative to Slack or Microsoft Teams chat for a small organization.

Why it fits:

- Familiar channel-based team chat experience.
- Strong self-hosted story.
- Good fit for project teams that want chat plus integrations.

Things to check before adding:

- Initial admin account bootstrap.
- SMTP and notification settings.
- Whether the community edition is enough for OpenDock defaults.
- Resource usage compared with lighter chat systems.

Reference:

- https://docs.mattermost.com/

#### Zulip

Zulip is a team chat system built around streams and topics. Its topic model makes long-running discussions easier to follow than normal chronological chat.

Commercial replacement angle:

- Alternative to Slack, Discord communities, or Microsoft Teams chat.

Why it fits:

- Excellent for organized async discussion.
- Strong open-source project with production deployment documentation.
- More structured than Slack-style rooms, which can be valuable for knowledge retention.

Things to check before adding:

- Docker support and whether OpenDock should use official production install guidance or community compose patterns.
- Outgoing email requirements.
- Initial organization and admin creation.
- Mobile push notification limitations for self-hosted servers.

Reference:

- https://zulip.readthedocs.io/

#### Rocket.Chat

Rocket.Chat is a broader communication platform with team chat, federation options, and customer-engagement style features.

Commercial replacement angle:

- Alternative to Slack, Microsoft Teams chat, Intercom-style customer chat, or omnichannel support tools.

Why it fits:

- Feature-rich communication platform.
- Official Docker Compose deployment documentation exists.
- Interesting if OpenDock later targets small business or community operations.

Things to check before adding:

- MongoDB dependency and operational weight.
- Licensing and feature split.
- Whether the scope is too broad for OpenDock's simple default experience.

Reference:

- https://docs.rocket.chat/

#### Matrix / Element

Matrix is an open standard for decentralized communication. Element is the most common client/server ecosystem entry point.

Commercial replacement angle:

- Alternative to Slack, Discord, WhatsApp groups, or federated community chat.

Why it fits:

- Federation and data ownership are philosophically aligned with OpenDock.
- Good fit for communities that want open communication infrastructure.

Things to check before adding:

- Server choice, likely Synapse, and operational complexity.
- Federation defaults.
- Identity, registration, moderation, and abuse controls.
- Whether it is too protocol-heavy for a first communication service.

Reference:

- https://matrix.org/docs/

#### Nextcloud Talk

Nextcloud Talk is already adjacent to OpenDock because Nextcloud is included. It adds chat, calls, screensharing, and collaboration features inside the existing Nextcloud ecosystem.

Commercial replacement angle:

- Alternative to Zoom, Google Meet, Microsoft Teams meetings, or lightweight Slack-style group communication.

Why it fits:

- Could strengthen the existing `cloud` group instead of adding another full communication stack.
- Natural fit if users already launch Nextcloud.
- Fewer new moving pieces than a separate chat platform.

Things to check before adding:

- Whether Talk should be enabled/configured by OpenDock or left to Nextcloud app management.
- TURN/STUN requirements for reliable calls.
- Push notification and mobile experience.

Reference:

- https://nextcloud.com/talk/

### groupware

Groupware is the broader "small organization operating system" category: mail, calendar, contacts, tasks, office documents, meetings, projects, CRM, and internal coordination.

This category is where the commercial replacement lens gets especially strong. A good OpenDock groupware stack can replace pieces of Google Workspace, Microsoft 365, Slack, Trello, Asana, Notion, Confluence, HubSpot, or Salesforce for a small group.

Possible groups:

```text
groupware: nextcloud mattermost bookstack openproject
crm: suitecrm
business: odoo
```

#### Nextcloud Hub

Nextcloud can be more than file sync. With Mail, Calendar, Contacts, Talk, Office, and related apps, it can become the center of a small groupware setup.

Commercial replacement angle:

- Alternative to Google Workspace, Microsoft 365, Dropbox, Google Drive, Google Calendar, and Google Meet.

Why it fits:

- Already included in OpenDock.
- Expanding the default Nextcloud story may provide more value than adding another large service.
- Good bridge between personal home server and small team groupware.

Things to check before expanding:

- Which apps should OpenDock configure by default, if any.
- Mail account setup expectations.
- Office integration choice.
- Talk TURN/STUN requirements.

Reference:

- https://nextcloud.com/

#### OpenProject

OpenProject is a project management platform with work packages, Gantt charts, boards, wiki pages, time tracking, meetings, and document management.

Commercial replacement angle:

- Alternative to Jira, Asana, Trello, Monday.com, or Microsoft Project.

Why it fits:

- Strong groupware value for teams.
- Clear project-management category.
- Complements chat and knowledge-base services.

Things to check before adding:

- Initial admin setup.
- SMTP and notification settings.
- Resource usage.
- Whether the community edition has enough value for OpenDock.

Reference:

- https://www.openproject.org/docs/

#### SOGo

SOGo is a classic open-source groupware server focused on webmail, calendars, and address books using open standards such as CalDAV and CardDAV.

Commercial replacement angle:

- Alternative to Microsoft Exchange, Google Workspace mail/calendar/contacts, or hosted groupware suites.

Why it fits:

- Strong standards-based groupware story.
- Useful for teams that want shared calendars and contacts.

Things to check before adding:

- Mail server dependency. OpenDock currently has outbound SMTP support, not a full inbound mail stack.
- User and domain management complexity.
- Whether it should wait until OpenDock has a clearer mail-hosting stance.

Reference:

- https://www.sogo.nu/

#### SuiteCRM

SuiteCRM is an open-source customer relationship management system.

Commercial replacement angle:

- Alternative to Salesforce, HubSpot CRM, or Microsoft Dynamics CRM.

Why it fits:

- Useful for small organizations, freelancers, clubs, and community projects with contacts, leads, events, and follow-ups.
- Strong "paid SaaS replacement" story.

Things to check before adding:

- Whether CRM belongs in OpenDock's default audience.
- Initial admin account setup.
- Mail integration and cron requirements.
- Backup expectations for attachments and database.

Reference:

- https://suitecrm.com/

#### Odoo Community

Odoo Community is a modular business-management suite covering areas such as CRM, sales, inventory, project management, website, and e-commerce.

Commercial replacement angle:

- Alternative to ERP/CRM/business SaaS suites such as Odoo Online, Zoho, Salesforce, Shopify-adjacent workflows, or lightweight ERP tools.

Why it fits:

- Huge "run your small business from home server" story.
- Many modules in one platform.

Things to check before adding:

- Community vs Enterprise feature split.
- Operational complexity and resource usage.
- Whether it is too business-heavy for OpenDock's default scope.

Reference:

- https://www.odoo.com/

### knowledge

Knowledge storage is a strong category for OpenDock. It maps directly to paid products such as Notion, Confluence, Coda, Evernote, and hosted team wikis. This category can include personal notes, structured documentation, outliners, bookmarks, and lightweight publishing.

Possible group:

```text
knowledge: bookstack outline linkding
```

#### BookStack

BookStack is a structured wiki organized around shelves, books, chapters, and pages.

Commercial replacement angle:

- Alternative to Confluence, Notion docs spaces, or a hosted internal wiki.

Why it fits:

- Friendly mental model for non-technical users.
- Good for household documentation, project notes, runbooks, and family knowledge.
- Strong "I can use this today" value after setup.

Things to check before adding:

- Initial admin account bootstrap.
- Mail settings and password reset flow.
- Backup expectations for uploads, database, and app key.

Reference:

- https://www.bookstackapp.com/docs/

#### Outline

Outline is a polished team knowledge base and wiki. It is probably the closest open-source candidate to the modern hosted team-wiki feel.

Commercial replacement angle:

- Alternative to Notion team docs, Slite, Confluence, or GitBook-style knowledge bases.

Why it fits:

- Excellent user experience.
- Strong fit for polished documentation and collaborative notes.
- Clear category leader for a modern wiki experience.

Things to check before adding:

- Authentication requirements. Outline commonly expects an external auth provider.
- Object storage requirements and whether local storage is acceptable for OpenDock defaults.
- Whether the setup can remain beginner-friendly.

Reference:

- https://docs.getoutline.com/

#### AppFlowy

AppFlowy is an open-source Notion-style workspace.

Commercial replacement angle:

- Alternative to Notion.

Why it fits:

- Strong "paid SaaS replacement" story.
- Good match for users who want databases, pages, and structured notes.

Things to check before adding:

- Self-hosted architecture and required components.
- Whether the server experience is mature enough for OpenDock defaults.
- Initial account and collaboration setup.

Reference:

- https://docs.appflowy.io/

#### Wiki.js

Wiki.js is a flexible wiki with broad storage, auth, and editing options.

Commercial replacement angle:

- Alternative to Confluence, hosted wiki services, or documentation portals.

Why it fits:

- Mature wiki category.
- Good for technical documentation and team-style knowledge bases.

Things to check before adding:

- Whether its configuration surface is too broad for OpenDock's simple defaults.
- Initial admin setup.
- Database and backup model.

Reference:

- https://docs.requarks.io/

#### SilverBullet

SilverBullet is a personal knowledge base with a local-first Markdown feel.

Commercial replacement angle:

- Alternative to Obsidian Sync, Roam-style personal knowledge tools, or lightweight hosted notes.

Why it fits:

- Good for technical users who like plain files and programmable notes.
- Smaller operational footprint than heavier team wiki systems.

Things to check before adding:

- Authentication and public exposure defaults.
- Data directory layout.
- Whether it is too technical for the default OpenDock audience.

Reference:

- https://silverbullet.md/

#### TriliumNext

TriliumNext is a hierarchical note-taking and personal knowledge-base app.

Commercial replacement angle:

- Alternative to Evernote, OneNote, or hosted personal note systems.

Why it fits:

- Strong personal knowledge-management use case.
- Better fit for private notes than public documentation.

Things to check before adding:

- Project maturity and release cadence.
- Backup and export story.
- Whether the first-run user flow is simple enough.

Reference:

- https://github.com/TriliumNext/Notes

#### Memos

Memos is a lightweight self-hosted memo and micro-note service.

Commercial replacement angle:

- Alternative to quick-note apps, private microblogging tools, or lightweight journaling SaaS.

Why it fits:

- Simple and approachable.
- Good "small useful app" for capturing thoughts, snippets, and daily notes.
- Lower operational burden than full wiki systems.

Things to check before adding:

- Initial account setup.
- Public/private sharing defaults.
- Backup and attachment handling.

Reference:

- https://www.usememos.com/

#### linkding

linkding is a small self-hosted bookmark manager.

Commercial replacement angle:

- Alternative to Pinboard, Raindrop.io, Pocket-style bookmark workflows, or browser-sync lock-in.

Why it fits:

- Lightweight.
- Simple category.
- Low operational burden compared with larger collaboration tools.

Things to check before adding:

- Initial user creation.
- Import/export path.
- Whether public registration must be disabled.

Reference:

- https://github.com/sissbruecker/linkding

### documents

#### Paperless-ngx

Paperless-ngx is the strongest next-service candidate. It adds a missing home-server category: searchable personal documents.

Why it fits:

- Clear everyday value: scan, OCR, tag, and search household documents.
- Complements Nextcloud and Immich without duplicating them.
- Has a concrete "it works" moment after setup: upload a document and search it.
- Supports multi-user use and workflow-style organization.

Things to check before adding:

- Required services and storage layout.
- OCR language configuration defaults.
- Mail import support and whether it should use common SMTP settings.
- Backup expectations for documents, database, and generated metadata.

Possible group:

```text
documents: paperless-ngx
```

Reference:

- https://docs.paperless-ngx.com/

### security

#### Vaultwarden

Vaultwarden provides a lightweight Bitwarden-compatible password vault. It is a high-value service, but it has a higher security bar than most OpenDock services.

Commercial replacement angle:

- Alternative to Bitwarden hosted plans, 1Password, Dashlane, or LastPass.

Why it fits:

- Strong "killer app" value for a personal server.
- Easy for users to understand because it maps to a common password-manager use case.
- Works well behind the existing HTTPS-first Cloudflare/Caddy model.

Things to check before adding:

- Registration policy should probably be closed or clearly controlled.
- Admin token handling must be generated safely and not printed casually.
- SMTP setup may matter for invitations and account flows.
- Documentation must be careful about backup, recovery, and public exposure.

Possible group:

```text
security: vaultwarden
```

Reference:

- https://github.com/dani-garcia/vaultwarden

### tools

#### Stirling PDF

Stirling PDF is a practical utility service for PDF merge, split, conversion, OCR, and related operations.

Commercial replacement angle:

- Alternative to Adobe Acrobat online tools, Smallpdf, iLovePDF, or other hosted PDF utilities.

Why it fits:

- Very easy to understand.
- Likely low-friction compared with account-heavy services.
- Useful even for a single user.
- Good candidate for a lightweight `tools` category.

Things to check before adding:

- Whether authentication should be enabled by default.
- Resource usage for OCR and conversion features.
- Whether the lightweight image is enough for OpenDock defaults.

Possible group:

```text
tools: stirling-pdf
```

Reference:

- https://docs.stirlingpdf.com/

## Good Candidates

### dev

#### Gitea

Gitea would add a self-hosted Git forge. It is useful for users who want private repositories on their own server, but it may overlap with GitHub for many people.

Why it fits:

- Mature Docker support.
- Clear category and URL.
- SMTP configuration can reuse common mail values if supported by official settings.

Things to check before adding:

- Initial admin account bootstrap.
- SSH port exposure expectations.
- Backup requirements for repositories, database, and attachments.

Possible group:

```text
dev: gitea
```

Reference:

- https://docs.gitea.com/installation/install-with-docker

### finance

#### Actual Budget

Actual Budget is a personal budgeting app. It has strong personal utility, but financial data raises the bar for security and backup guidance.

Commercial replacement angle:

- Alternative to YNAB, Monarch Money, Copilot Money, or hosted budgeting apps.

Why it fits:

- Clear single-purpose app.
- Complements the personal home-server story.
- Useful even without multiple users.

Things to check before adding:

- Authentication and sync-server model.
- Backup and restore flow.
- Whether exposing it publicly by default is appropriate.

Possible group:

```text
finance: actual
```

Reference:

- https://actualbudget.org/

## Special Consideration

### home

#### Home Assistant

Home Assistant is a major self-hosted application, but it may not be a clean OpenDock default. The Home Assistant ecosystem is strongest with Home Assistant OS, Supervisor, and add-ons, while a plain Docker container can feel more limited than users expect.

Why it might fit:

- Extremely strong category leader.
- Natural home-server association.

Why it might not fit yet:

- Docker-only installation has different expectations than the full Home Assistant OS experience.
- Hardware, discovery, USB, host networking, and add-on expectations can make the setup more host-specific.

Possible group:

```text
home: home-assistant
```

Reference:

- https://www.home-assistant.io/installation/linux

## Current Recommendation

Start with Paperless-ngx or a knowledge app.

Recommended first addition:

```text
documents: paperless-ngx
```

Recommended first knowledge addition:

```text
knowledge: bookstack
```

Reasoning:

- It fills a missing category.
- It has obvious home-server value.
- It complements existing OpenDock services.
- It is less security-sensitive than Vaultwarden and less ecosystem-specific than Home Assistant.
- BookStack is the safest first knowledge candidate because its mental model is simple and its setup should be easier than Outline or AppFlowy.

After that, consider Outline if OpenDock is ready to handle auth complexity, Vaultwarden if OpenDock is ready to treat security-sensitive defaults very carefully, or Stirling PDF if the goal is a smaller low-friction utility addition.
