import fs from 'node:fs';
const [file, der] = process.argv.slice(2);
const j = JSON.parse(fs.readFileSync(file, 'utf8'));
const bad = [];
if (j.verdict !== 'PASS-REVIEWED-DIFFS' && j.verdict !== 'PASS-BYTE-IDENTICAL') bad.push('verdict ' + j.verdict);
if (j.unexpected && j.unexpected.length) bad.push('unexpected ' + j.unexpected.length);
if (!j.verifyPkg || !j.verifyPkg.cand || j.verifyPkg.cand.all !== true) bad.push('verify_pkg candidate not all-pass');
if (j.verifyPkg && j.verifyPkg.ref && j.verifyPkg.ref.all !== true) bad.push('verify_pkg reference not all-pass');
if (!j.apkKey || !j.apkKey.cand || j.apkKey.cand.derSha256 !== der) bad.push('embedded apk key != pinned local PEM');
if (j.apkKey && j.apkKey.privateKeyLeaks && j.apkKey.privateKeyLeaks.length) bad.push('private key material in rootfs');
console.log(JSON.stringify({ verdict: j.verdict, expected: (j.expected || []).length, allowed: (j.allowed || []).length, unexpected: (j.unexpected || []).length, kernelDataIdentical: j.kernelDataIdentical, apkKey: j.apkKey && j.apkKey.cand && j.apkKey.cand.derSha256 }, null, 1));
if (bad.length) { console.error('BAD: ' + bad.join('; ')); process.exit(1); }
process.exit(0);