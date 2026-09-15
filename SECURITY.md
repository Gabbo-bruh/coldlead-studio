# Security Policy

## Reporting a vulnerability

Please **do not open a public issue**. Use GitHub's
[private vulnerability reporting](https://docs.github.com/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository. You will get an answer within a few days.

## Notes for users

- The dashboard (`coldlead web`) has no authentication and binds to `127.0.0.1` by default. Do not
  expose it on a public interface.
- API keys are read from the environment or a local `.env` file, which is git-ignored. Never
  commit them.
- Data scraped from third-party websites is rendered with automatic HTML escaping in the dashboard.

## SSRF protection in website audits

`coldlead audit`, the `coldlead_audit` / `coldlead_score` MCP tools and `scout` fetch URLs that
come from third parties — map data, imported lists, or an AI agent that may have read a hostile
page. The auditor (`src/coldlead/enrich/tech_audit.py`) therefore:

- accepts only `http` and `https` URLs;
- resolves the host first and refuses loopback, private, link-local (including cloud metadata
  such as `169.254.169.254`), multicast, reserved, unspecified and shared addresses — also when
  wrapped in IPv4-mapped or 6to4 IPv6 — if **any** resolved address is non-public;
- follows redirects by hand and re-checks every hop;
- validates the address again at connection time and connects to that exact address, so a DNS
  answer cannot change between the check and the connection (DNS rebinding);
- reads at most 5 MB of any response (512 KB for `robots.txt`), so a huge or endless page cannot
  exhaust memory.

When a system proxy is configured (`HTTP_PROXY` / `HTTPS_PROXY`), the proxy opens the connection:
the per-hop checks still apply, the connection-time check is the proxy's responsibility.
