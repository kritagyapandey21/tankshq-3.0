# AUROX Deployment Context

## Repository

- GitHub: `https://github.com/kritagyapandey21/AUROX`
- VPS checkout: `/var/www/aurox`
- Latest deployment commits include the timezone feature, Hostinger setup, backend isolation, `/pocketoption/` routing, context documentation, the single-ID bypass, and the writable preference database fix.

## Production Architecture

- Domain: `tradingsignal.in`
- Login URL: `https://tradingsignal.in/pocketoption/`
- Frontend: `/var/www/aurox/frontend`
- Backend service: `aurox-backend`
- Backend bind address: `127.0.0.1:8001`
- Nginx proxies `/api/` to port `8001` and serves the frontend under `/pocketoption/`.
- HTTPS is installed with Let's Encrypt.
- The existing website on the VPS must remain isolated and unchanged.
- AUROX must not use the other website's ports, files, Nginx server block, or domain configuration.

## Implemented Features

- Searchable IANA timezone selector at login.
- Trader timezone preference persisted by Trader ID in SQLite.
- Existing Trader ID verification remains unchanged.
- Optional single-ID bypass is configured privately with `BYPASS_TRADER_ID`; all other IDs require Telegram verification.
- Existing traders default to `Asia/Kolkata`.
- Signal API includes absolute ISO timestamps while preserving legacy time fields.
- Frontend displays timezone-converted times without showing dates.
- Countdown uses absolute timestamps and is independent of display timezone.
- Pocket Option integration remains the signal data source.
- Charts use Pocket Option 1-minute candle close prices received through BinaryOptionsToolsV2, cached by the backend, returned as `chart_candles`, and drawn by the frontend Canvas.
- Signal timing is generated explicitly in `Asia/Kolkata`; user timezone changes affect display only.
- Visible entry, expiry, and generated times show time only; absolute ISO timestamps remain in API responses for countdown correctness.
- The preference database is stored in `/var/lib/aurox/trader_preferences.sqlite3` so the `www-data` service can write it safely.

## Authentication

- Existing Trader ID login remains the authentication flow.
- `BYPASS_TRADER_ID` in the private VPS `.env` allows exactly one trusted Trader ID to bypass Telegram verification.
- Every other Trader ID is checked through the existing Telegram verification service.
- The bypass response is verified working for the configured trusted ID.

## Production Status

The public website, HTTPS, backend health endpoint, Trader ID bypass, and Pocket Option data connection are working. The latest service log shows:

```text
PO data loop: connected via BinaryOptionsToolsV2
```

The production login URL is:

```text
https://tradingsignal.in/pocketoption/
```

The API is available under `/api`, for example:

```text
https://tradingsignal.in/api/health
https://tradingsignal.in/api/signal
```

## Maintenance

If the Pocket Option session expires:

1. Obtain a fresh Pocket Option WebSocket `42["auth", ...]` session token.
2. Replace only `LO_UID` in `/var/www/aurox/backend/.env`.
3. Keep `.env` private and set permissions to `600`.
4. Restart and inspect the service:

```bash
systemctl restart aurox-backend
journalctl -u aurox-backend -f
```

5. Confirm the log contains a successful Pocket Option connection.
6. Verify:

```bash
curl https://tradingsignal.in/api/health
curl https://tradingsignal.in/api/signal
```

Do not store or commit Telegram, Pocket Option, or other credential values in this file. Previously exposed credentials should be rotated.
