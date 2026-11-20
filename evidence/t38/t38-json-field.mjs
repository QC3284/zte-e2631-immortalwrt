import fs from 'node:fs';
const [file, field] = process.argv.slice(2);
const j = JSON.parse(fs.readFileSync(file, 'utf8'));
let v = j;
for (const k of field.split('.')) { if (v == null) break; v = v[k]; }
console.log(String(v));