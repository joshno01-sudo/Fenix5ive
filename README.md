# Fenix 5ive — Website Redesign

A bold, modern redesign concept for [fenix5ive.com](https://fenix5ive.com) — the custom vinyl,
graphics, and window tint shop in Cottage Hills, Illinois.

**BE BOLD. History favors the bold.**

## What's here

A fast, dependency-free static site (no build step, no framework) that replaces the current
GoDaddy Website Builder site with a design worthy of the brand:

- **Dark, fire-accented design** built around the phoenix logo's red/orange/gold palette
- **Full-screen hero** with animated headline and slow cinematic zoom
- **Interactive window-tint simulator** — drag a slider to preview VLT levels live
- **Animated wrap-advertising stats** (30–70K daily impressions, $0.04 CPM, 7-year wrap life)
- **All original content preserved**: services, film types, art-team story, community values,
  additional products, and full contact details
- **Mobile-first responsive** with slide-in navigation, tap-to-call / tap-to-text contact cards
- Scroll-reveal animations with `prefers-reduced-motion` support
- SEO meta + Open Graph tags

## Structure

```
index.html        — the whole site (single page, anchored sections)
css/style.css     — design system + layout
js/main.js        — nav, scroll reveals, counters, tint simulator
assets/img/       — optimized imagery pulled from the current site
FenixVault/       — the shop's Windows backup program (separate from the site)
```

## Fenix Vault

Also in this repository: **[Fenix Vault](FenixVault/)**, a Windows backup
program for the shop. It copies personal and business files — artwork, cut
files, print files, invoices, photos, fonts, email — onto any drive you plug
in, keeping the folder structure exactly as it is, and puts it all back on
another PC from a single double-click. Nothing to do with the website; it just
lives here too.

## Run it locally

Just open `index.html` in a browser, or serve it:

```bash
python3 -m http.server 8000
# → http://localhost:8000
```

## Deploy

Works anywhere static files are served — GitHub Pages, Netlify, Cloudflare Pages, or any
web host. For GitHub Pages: Settings → Pages → deploy from branch, root folder.

## Notes for going live

- Replace remaining stock photos with real photos of Fenix 5ive's work (wrapped vehicles,
  tint jobs, signs) — the design gets even stronger with genuine project shots.
- The contact section links directly to phone (1-618-251-4221), text (1-618-917-4491),
  email, and Google Maps directions.
- Social links point to the shop's existing Facebook and Instagram pages.
