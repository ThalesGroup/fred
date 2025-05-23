Describe here all the security policies in place on this repository to help your contributors to handle security issues efficiently.

## Goods practices to follow

:warning:**You must never store credentials information into source code or config file in a GitHub repository**
- Block sensitive data being pushed to GitHub by git-secrets or its likes as a git pre-commit hook
- Audit for slipped secrets with dedicated tools
- Use environment variables for secrets in CI/CD (e.g. GitHub Secrets) and secret managers in production

# Security Policy

## Supported Versions

No versions of this project is currently being supported with security updates. 
This will only occur when a first official 0.1 release is reached.


## Reporting a Vulnerability

This said do not hesitate to report security issues. The github project (and gitlab mirrors) are equiped with dependabots.
Feel free to use your own tooling to analyse the code. We will be prompt to remove the vulnerabilities. Fell free to 
propose update on your own that we will happily integrate. 

## Disclosure policy

Define the procedure for what a reporter who finds a security issue needs to do in order to fully disclose the problem safely, including who to contact and how.

## Security Update policy

Define how you intend to update users about new security vulnerabilities as they are found.

## Security related configuration

Settings users should consider that would impact the security posture of deploying this project, such as HTTPS, authorization and many others.

## Known security gaps & future enhancements

Security improvements you haven’t gotten to yet.
Inform users those security controls aren’t in place, and perhaps suggest they contribute an implementation
