# Nginx Configuration for Xiugua Backend

Nginx serves as a TLS-terminating reverse proxy in front of the uvicorn ASGI server running on `127.0.0.1:8000`. The backend never exposes HTTP directly to the internet; all traffic arrives over HTTPS through Nginx.

## Installation

### Prerequisites

- Ubuntu 22.04+ on Tencent Cloud ECS
- Nginx 1.18+ (`sudo apt install nginx`)
- Certbot for Let's Encrypt SSL (`sudo apt install certbot python3-certbot-nginx`)
- A DNS A record pointing `xiugua-reading.cn` and `www.xiugua-reading.cn` to the ECS public IP

### Steps

```bash
# 1. Copy the config to Nginx sites-available
sudo cp deploy/nginx/xiugua.conf /etc/nginx/sites-available/xiugua

# 2. Enable the site
sudo ln -sf /etc/nginx/sites-available/xiugua /etc/nginx/sites-enabled/

# 3. (Optional) Remove the default site
sudo rm -f /etc/nginx/sites-enabled/default

# 4. Test configuration
sudo nginx -t

# 5. Reload Nginx
sudo systemctl reload nginx
```

## SSL Certificate (Let's Encrypt)

### Initial Setup

```bash
# Obtain certificate (Nginx plugin auto-detects config)
sudo certbot --nginx -d xiugua-reading.cn -d www.xiugua-reading.cn

# Verify auto-renewal
sudo certbot renew --dry-run
```

### Automatic Renewal

Certbot installs a systemd timer by default (`systemctl list-timers | grep certbot`). The certificate is renewed automatically when close to expiry. No manual action needed.

### Manual Renewal

```bash
sudo certbot renew
sudo systemctl reload nginx
```

## Configuration Overview

| Directive               | Value          | Purpose                      |
|-------------------------|----------------|------------------------------|
| `listen 80`             | Redirect 301   | Force HTTPS                  |
| `listen 443 ssl http2`  | TLS + HTTP/2   | Secure traffic               |
| `ssl_certificate`       | Let's Encrypt  | Free TLS certificate         |
| `client_max_body_size`  | 50M            | Allow large book uploads     |
| `proxy_read_timeout`    | 120s           | Long-running LLM requests    |
| HSTS                    | 6 months       | Enforce HTTPS at browser     |
| X-Frame-Options         | DENY           | Clickjacking protection      |
| X-Content-Type-Options  | nosniff        | MIME sniffing prevention     |
| Cache-Control (/api/)   | no-store       | Disable caching for API      |

## Testing

```bash
# Verify HTTPS is working
curl -I https://xiugua-reading.cn/health

# Verify HTTP redirects to HTTPS
curl -I http://xiugua-reading.cn/health

# Check security headers
curl -sI https://xiugua-reading.cn/health | grep -E '^(Strict-Transport|X-Frame|X-Content|Referrer)'
```

## Troubleshooting

- **502 Bad Gateway**: uvicorn may not be running. Check `systemctl status xiugua`.
- **SSL certificate expired**: Run `sudo certbot renew && sudo systemctl reload nginx`.
- **Upload fails with 413**: Check the `client_max_body_size` directive matches your needs.
- **Config test fails**: Common cause is a missing SSL certificate path. Run certbot first.
