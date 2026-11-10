# Macro Intelligence — website

Static React + TypeScript + Vite + Tailwind site that renders the JSON bundle exported by the pipeline
(`macro-intel run` → `../data/site/*.json`). See the root [README](../README.md) and
[docs/ARCHITECTURE.md §10](../docs/ARCHITECTURE.md).

```bash
npm install
npm run dev      # serves ../data/site at /data (override: MACRO_SITE_DIR=...)
npm run build    # tsc type-check + build; copies the data bundle into dist/data
```
