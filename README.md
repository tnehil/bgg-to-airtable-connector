# BGG to Airtable connector

Sync a user's boardgamegeek collection to airtable for fun analysis!

## BGG API notes

BoardGameGeek has an XML API for accessing both game and user data. It's
documented here:

-   https://boardgamegeek.com/wiki/page/BGG_XML_API2

To access a specific user's plays, the endpoint is:

-   https://boardgamegeek.com/xmlapi2/plays?username=<username>

To get private collection info, e.g. acquisition date or price paid,
the user has to be logged in. There is no API key. So the session
that accesses the collection endpoint first has to log in to the site.
This is explained in a BGG thread:

-   https://boardgamegeek.com/thread/2182271/programmatic-login-and-collection-update-scripts

Getting item details now requires an API token. It should be stored in
an env variable called BGGTOKEN.

## Running the sync

This syncs a BoardGameGeek collection (including private info) to Airtable.
It runs locally on a Mac via launchd. It does not run on GitHub Actions:
BGG's Cloudflare blocks the login request from GitHub-hosted runner IPs
(HTTP 403), so the script can't authenticate there.

### Run manually

```bash
set -a; source ~/.config/bgg-sync/env; set +a
uv run main.py
```

Requires Python 3.12+ (`itertools.batched`). Set `LOG_LEVEL=DEBUG` for more detail.

### Scheduled setup (macOS launchd)

Note: the script runs off the installed copy and not the repo copy,
so changes to the repo copy must be copied over before they take effect.

1. Create the env file from `launchd/env.example`:
   ```bash
   mkdir -p ~/.config/bgg-sync
   cp launchd/env.example ~/.config/bgg-sync/env
   chmod 600 ~/.config/bgg-sync/env   # then fill in values
   ```
2. Copy the wrapper and edit `REPO` and `UV` at the top:
   ```bash
   cp launchd/run.sh ~/.config/bgg-sync/run.sh
   chmod +x ~/.config/bgg-sync/run.sh
   ```
3. Copy the plist, replace `YOURNAME` with your username (absolute paths only,
   launchd doesn't expand `~`), then load it:
   ```bash
   cp launchd/com.user.bgg-sync.plist ~/Library/LaunchAgents/
   launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.user.bgg-sync.plist
   ```

Runs daily at 9:00. If the Mac is asleep then, it runs on wake; if it's
powered off, that day's run is skipped.

### Operations

| Task | Command |
|---|---|
| Run now | `launchctl kickstart -k gui/$(id -u)/com.user.bgg-sync` |
| Check status / last exit code | `launchctl print gui/$(id -u)/com.user.bgg-sync` |
| Reload after editing the plist | `launchctl bootout gui/$(id -u)/com.user.bgg-sync`, then `bootstrap` again |
| Logs | `~/.config/bgg-sync/out.log`, `err.log` |

### Troubleshooting

- **`Bootstrap failed: 5: Input/output error`**: the job is usually already loaded. Run `bootout` and retry. Otherwise check `plutil -lint` on the plist.
- **"Operation not permitted" in err.log**: the repo is in a macOS-protected folder (Documents, Desktop, Downloads). Move it elsewhere, e.g. `~/code`.
- **Airtable looks stale**: check `out.log` for the last run and `launchctl print` for the last exit code. There's no alerting, so staleness is the signal.
- **Login 403**: BGG/Cloudflare is blocking the IP. This is why it can't run from datacenter IPs.