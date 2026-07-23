const fs = require('fs');
const p = fs.readFileSync('C:/Users/omerguzel/fabric-demo-gallery/frontend/src/lib/presenterContent.ts', 'utf8');
const c = fs.readFileSync('C:/Users/omerguzel/fabric-demo-gallery/frontend/src/lib/demoCatalog.ts', 'utf8');
const ids = (t) => [...t.matchAll(/^  ['"]?([a-z][a-z-]+)['"]?: \{/gm)].map((m) => m[1]);
const pi = ids(p), ci = ids(c);
console.log('presenter ids (' + pi.length + '):', pi.join(', '));
console.log('catalog ids (' + ci.length + '):', ci.join(', '));
console.log('MISSING guide:', ci.filter((x) => !pi.includes(x)).join(', ') || 'none');
