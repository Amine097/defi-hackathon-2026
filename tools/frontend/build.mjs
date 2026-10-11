// Dev-only build: bundles the landing hero (Three.js + GSAP, tree-shaken) into one committed, minified ES module.
import { build } from 'esbuild';
const r = await build({
  entryPoints: ['src/landing.js'],
  bundle: true, format: 'esm', minify: true, target: ['es2020'], legalComments: 'linked',
  outfile: '../../public/assets/js/landing/landing.bundle.js', metafile: true, logLevel: 'warning',
});
const out = Object.entries(r.metafile.outputs).map(([f, o]) => `${f} ${(o.bytes / 1024).toFixed(0)} KB`);
console.log(out.join('\n'));
