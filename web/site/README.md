# Local Zephyr homepage

`index.html` preserves the design, inline SVG artwork, procedural 3D spacecraft and wavelength guide from the user's `zephyr_spherex_planet_x_interactive.html`. The IR Lab navigation, Explore SPHEREx button and Data Explorer card lead to `/lab` on the same local Python server.

Runtime assets are vendored. No Tailwind CDN execution or JavaScript CDN access is needed. The Google font stylesheet is optional: system sans-serif fonts remain usable without internet access. `assets/theme.css` shares Zephyr typography, navigation, spacing, subtle space background and red accent with the laboratory.

Rebuild from this directory with Node.js 22+:

```powershell
npm.cmd ci --ignore-scripts --no-audit --no-fund
npm.cmd run build
npm.cmd run check
```

The build pins Tailwind CSS 3.4.17 and Three.js 0.128.0, copies the exact npm distribution files corresponding to the reference CDN URLs, compiles the homepage utilities, records SHA-256 digests in `assets/manifest.json`, and checks local links/assets and inline JavaScript syntax. MIT notices remain in `assets/three-LICENSE.txt` and `assets/tailwind-LICENSE.txt`.

Serve `index.html` at `/` and `assets/*` at `/site-assets/*`. Do not expose `node_modules`. `/lab` remains the Python-backed science interface.

The existing homepage uses inline scripts, styles and click handlers. Its CSP needs `script-src 'self' 'unsafe-inline'`, `style-src 'self' 'unsafe-inline' https://fonts.googleapis.com`, `font-src 'self' https://fonts.gstatic.com`, `img-src 'self' data:`, and `connect-src 'self'`. No eval or external script domains are required. The lab can keep the stricter `script-src 'self'` policy because its own code is external.
