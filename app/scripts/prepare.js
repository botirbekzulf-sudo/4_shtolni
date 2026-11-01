// Копирует игру в www и кладёт библиотеки внутрь приложения вместо загрузки с CDN
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');
const www = path.join(root, 'www');
const lib = path.join(www, 'lib');

(async () => {
  fs.mkdirSync(lib, { recursive: true });
  let html = fs.readFileSync(path.join(root, '..', 'index.html'), 'utf8');
  const urls = [...html.matchAll(/<script src="(https:[^"]+)"><\/script>/g)].map(m => m[1]);
  if (!urls.length) throw new Error('В index.html не найдены библиотеки');
  for (const url of urls) {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`Не удалось скачать ${url}: ${res.status}`);
    const name = path.basename(new URL(url).pathname);
    fs.writeFileSync(path.join(lib, name), Buffer.from(await res.arrayBuffer()));
    html = html.replace(url, `lib/${name}`);
    console.log('Библиотека:', name);
  }
  fs.writeFileSync(path.join(www, 'index.html'), html);
  console.log('Готово: www/index.html');
})().catch(e => { console.error(e); process.exit(1); });
