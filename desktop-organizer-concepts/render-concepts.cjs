const path = require('path');
const { pathToFileURL } = require('url');
const { chromium } = require('playwright');

(async () => {
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
  } catch (_) {
    browser = await chromium.launch({ channel: 'msedge', headless: true });
  }

  const page = await browser.newPage({ viewport: { width: 922, height: 1032 }, deviceScaleFactor: 1.35 });
  await page.goto(pathToFileURL(path.join(__dirname, 'index.html')).href, { waitUntil: 'load' });
  await page.waitForTimeout(300);
  await page.screenshot({ path: path.join(__dirname, 'renders', 'concept-separated-v3.png'), fullPage: true });
  await page.locator('#add-task').click();
  await page.waitForTimeout(420);
  await page.screenshot({ path: path.join(__dirname, 'renders', 'concept-task-schedule-v3.png'), fullPage: true });
  await browser.close();
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
