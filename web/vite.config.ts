import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vite'

const here = path.dirname(fileURLToPath(import.meta.url))
// The pipeline exports the site bundle to ../data/site (override with MACRO_SITE_DIR, e.g. ../data-sample/site).
const siteDir = path.resolve(here, process.env.MACRO_SITE_DIR ?? '../data/site')

/** Serves the exported JSON bundle at /data in dev, and copies it into dist/data on build. */
function macroData(): Plugin {
  return {
    name: 'macro-data',
    configureServer(server) {
      server.middlewares.use('/data', (req, res, next) => {
        const rel = decodeURIComponent((req.url ?? '').split('?')[0]).replace(/^\/+/, '')
        const file = path.resolve(siteDir, rel)
        if (!file.startsWith(siteDir + path.sep) || !file.endsWith('.json') || !fs.existsSync(file)) return next()
        res.setHeader('Content-Type', 'application/json; charset=utf-8')
        res.setHeader('Cache-Control', 'no-store')
        fs.createReadStream(file).pipe(res)
      })
    },
    closeBundle() {
      if (process.env.SKIP_DATA_COPY) return
      if (!fs.existsSync(siteDir)) {
        this.warn(`No site data at ${siteDir}; dist/data not populated (run \`macro-intel run\` first)`)
        return
      }
      const out = path.resolve(here, 'dist/data')
      fs.mkdirSync(out, { recursive: true })
      for (const f of fs.readdirSync(siteDir)) {
        if (f.endsWith('.json')) fs.copyFileSync(path.join(siteDir, f), path.join(out, f))
      }
    },
  }
}

export default defineConfig({
  plugins: [react(), tailwindcss(), macroData()],
  base: './',
})
