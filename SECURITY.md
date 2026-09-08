# Security Policy

## Reporting a Vulnerability

Please do not open a public GitHub issue for security vulnerabilities.

Use GitHub's private vulnerability reporting feature to submit a report directly to the maintainers.

When reporting a vulnerability, please include:

- Description of the issue
- Steps to reproduce
- Potential impact
- Relevant logs or examples (with secrets removed)

## Security Considerations

Qoffee is designed with the following principles:

- Credentials are provided through environment variables or GitHub Actions secrets
- Secrets should never be stored in source code
- Logs should not expose tokens, webhook URLs, job IDs, or CRNs
- Qoffee runs within the user's own infrastructure

## Supported Versions

| Version | Supported |
| --- | --- |
| Latest release | Yes |
| Older releases | Best effort |