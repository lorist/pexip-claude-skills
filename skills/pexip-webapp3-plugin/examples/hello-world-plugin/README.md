# Hello World Plugin

Minimal Pexip webapp3 plugin demonstrating:

- Plugin registration with `registerPlugin`
- Toolbar button with `addButton`
- Toast notifications with `showToast`
- Conference event subscription with `authenticatedWithConference`

## Build

```bash
npm install
npm run build
```

Output: `dist/` folder ready to install into a branding ZIP at
`plugins/hello-world/`.

## Install

See `references/management-api-brandings.md` for the complete installation
flow (download branding → inject plugin → re-upload → route alias).
