# Temporary Cloudflare link

Double-click **start_cloudflare.bat** in this project folder.

The launcher finds cloudflared, reuses this project's dashboard on port 8001 or starts it, requests a Quick Tunnel, prints the HTTPS link, saves it to **runtime/cloudflare-link.txt**, and opens it in your browser. Sign in using your usual portal account. A Gemini key is not required to start the portal; configure AI after signing in if needed.

Keep the launcher window and computer running. Press Ctrl+C to stop sharing. The dashboard stays available locally. Each new tunnel normally receives a different link. These temporary tunnels are for demonstrations/testing, not permanent hosting. Cloudflare documentation: https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/

cloudflared is already installed on this computer. On another computer install it with `winget install --id Cloudflare.cloudflared -e`, or put cloudflared.exe in the project folder. Set up the Python environment using README first.

Optional commands:

- `start_cloudflare.bat -CheckOnly`: check prerequisites and server compatibility; creates no public tunnel.
- `start_cloudflare.bat -NoBrowser`: print/save the link without opening a browser.
- `start_cloudflare.bat -Port 8002`: use a different local port.

Only one sharing launcher can run per project. It never terminates an unrelated server. If an older server occupies the port, stop it and rerun the launcher. An administrator account must already be created locally before sharing.

The launcher registers only the exact generated HTTPS origin, refreshes its short expiry while running, and removes its registration when stopped normally. Portal sessions use Secure cookies through that origin. Cross-origin protection and normal role authorization remain active.

Troubleshooting logs are runtime/cloudflare-tunnel.err.log and runtime/cloudflare-server.err.log. If an existing cloudflared configuration prevents Quick Tunnels, consult the Cloudflare documentation; the launcher does not rename or delete your configuration.
