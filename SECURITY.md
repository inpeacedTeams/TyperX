# Security

TyperX is local-first. It has no network client, analytics, updater or account system. Templates and settings are stored in `%APPDATA%\TyperX`; logs contain lifecycle errors only and never message text.

The typing engine locks onto the foreground window captured at launch. If focus changes, input stops before the next key. `F9` is a global emergency stop.

Report vulnerabilities privately through GitHub Security Advisories. Do not open a public issue with exploit details.
