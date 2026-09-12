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
