const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require('C:/Users/36144/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
(async () => {
  const root = path.resolve(__dirname, '..');
  const browser = await chromium.launch({headless: true});
  const page = await browser.newPage({viewport: {width: 1120, height: 1100}, deviceScaleFactor: 2});
  await page.goto(pathToFileURL(path.join(__dirname, 'irc_architecture.html')).href);
  await page.locator('#architecture').screenshot({path: path.join(root, '.codex-output', 'irc_architecture.png')});
  await browser.close();
})().catch(error => { console.error(error); process.exitCode = 1; });
