# SSL certificate expired

## Symptoms
- Browsers show "Your connection is not private" or `NET::ERR_CERT_DATE_INVALID`.
- `curl` fails with `SSL certificate problem: certificate has expired`.
- Services calling each other fail with `x509: certificate has expired or is not yet valid`.
- The monitoring alert "Certificate expires in less than 14 days" fires.

## Likely causes
- Automatic renewal failed (cert-manager in Kubernetes, or certbot on a VM).
- The certificate was renewed, but the web server or ingress still serves the old one because it wasn't reloaded.
- The wrong certificate or an incomplete chain (missing intermediate certificate) is deployed.
- The ACME challenge fails: DNS record missing, or the HTTP challenge path is blocked.
- Let's Encrypt rate limits after too many failed attempts.
- The client's clock is wrong, so a valid certificate looks expired.

## How to diagnose
Check what certificate the server actually returns:

```bash
echo | openssl s_client -connect app.example.com:443 -servername app.example.com 2>/dev/null \
  | openssl x509 -noout -dates -subject -issuer
curl -vI https://app.example.com 2>&1 | grep -i -E "expire|subject|issuer"
```

`notAfter` is the expiry date. If it's in the future but clients still fail, check the chain and the client's clock (`date`).

In Kubernetes with cert-manager:

```bash
kubectl get certificate -A
kubectl describe certificate <name> -n <namespace>
kubectl get certificaterequest,order,challenge -n <namespace>
kubectl logs -n cert-manager deploy/cert-manager --tail 100
```

`READY=False` on the certificate, or a challenge stuck in `pending`, shows where renewal stopped.

On a VM with certbot:

```bash
sudo certbot certificates
sudo certbot renew --dry-run
```

## Fix
- **certbot:** renew and reload the web server:
  ```bash
  sudo certbot renew
  sudo systemctl reload nginx
  ```
- **cert-manager:** fix the reason the challenge fails (DNS record, ingress rule), then force a renewal with `cmctl renew <name> -n <namespace>`, or delete the certificate's Secret so cert-manager issues a new one.
- **Renewed but old certificate still served:** reload nginx, or restart the ingress controller pods if they didn't pick up the new Secret.
- **Missing chain:** configure the server to use the full chain file (`fullchain.pem`), not only the certificate.
- Check again with the `openssl` command above after the fix.

Never commit private keys to git, and never paste them into tickets or chat.

## Escalate if
- The certificate is managed by another team or bought from a commercial CA. Contact the Platform team.
- It's a wildcard certificate used by many services.
- A customer-facing domain can't be fixed within 30 minutes. Declare a SEV2 (see "Incident and escalation process").
