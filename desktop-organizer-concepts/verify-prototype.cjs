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

  const page = await browser.newPage({ viewport: { width: 922, height: 1032 } });
  page.setDefaultTimeout(6000);
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(pathToFileURL(path.join(__dirname, 'index.html')).href);
  await page.evaluate(() => localStorage.removeItem('desk-all-time-completed'));
  await page.reload();

  const todo = page.locator('[data-widget="todo"]');
  await todo.locator('.menu-button').click();
  const compactButton = todo.locator('[data-menu-action="compact"]');
  const menuTextBefore = await compactButton.textContent();
  const menuTextFits = await compactButton.evaluate(element => element.scrollWidth <= element.clientWidth);
  await compactButton.click();
  const menuTextAfter = await compactButton.textContent();

  await page.locator('#add-task').click();
  await page.waitForTimeout(380);
  const editorVisible = await todo.evaluate(element => element.classList.contains('editing'));
  await page.locator('#task-title').fill('每周整理学习笔记');
  await page.locator('#task-start').fill('2026-08-11');
  await page.locator('#task-end').fill('2026-08-31');
  await page.locator('#task-repeat').selectOption('weekly');
  await page.locator('#weekday-field input[value="三"]').check();
  await page.locator('#reminder-enabled').check();
  await page.locator('#reminder-time').fill('19:45');
  await page.locator('#save-task').click();
  await page.waitForTimeout(420);

  const newTask = page.locator('#task-list .task').last();
  const newTaskDetails = await newTask.locator('small').textContent();
  const allTimeAfterAdd = await page.locator('#all-time-count').textContent();

  await page.locator('#repeat-task .task-check').click();
  await page.waitForTimeout(760);

  const result = {
    widgetCount: await page.locator('.widget').count(),
    menuTextBefore,
    menuTextAfter,
    menuTextFits,
    editorVisible,
    editorClosedAfterSave: !(await todo.evaluate(element => element.classList.contains('editing'))),
    newTaskTitle: await newTask.locator('strong').textContent(),
    newTaskDetails,
    newTaskRepeat: await newTask.getAttribute('data-repeat'),
    todaySummary: await page.locator('.summary-title').textContent(),
    totalSummary: await page.locator('.progress-copy').textContent(),
    allTimeAfterAdd,
    completedCount: await page.locator('#done-count').textContent(),
    finalAllTimeCount: await page.locator('#all-time-count').textContent(),
    completionToast: await page.locator('#toast-copy').textContent(),
    repeatTaskExited: await page.locator('#repeat-task').evaluate(element => element.classList.contains('completed')),
    remainingCopy: await page.locator('#remaining-copy').textContent(),
    javascriptErrors: errors,
  };

  console.log(JSON.stringify(result, null, 2));
  await browser.close();

  if (
    result.widgetCount !== 3 ||
    result.menuTextBefore.trim() !== '紧凑模式：关' ||
    result.menuTextAfter.trim() !== '紧凑模式：开' ||
    !result.menuTextFits ||
    !result.editorVisible ||
    !result.editorClosedAfterSave ||
    result.newTaskTitle.trim() !== '每周整理学习笔记' ||
    !result.newTaskDetails.includes('2026.08.11—2026.08.31') ||
    !result.newTaskDetails.includes('每周（一、三）') ||
    !result.newTaskDetails.includes('19:45 提醒') ||
    result.newTaskRepeat !== 'weekly' ||
    !result.todaySummary.includes('今日完成 3 项') ||
    !result.totalSummary.includes('总共完成') ||
    result.allTimeAfterAdd.trim() !== '36' ||
    result.completedCount.trim() !== '3' ||
    result.finalAllTimeCount.trim() !== '37' ||
    result.completionToast.trim() !== '今日已完成，明天继续' ||
    !result.repeatTaskExited ||
    result.remainingCopy.trim() !== '还有 3 项' ||
    result.javascriptErrors.length
  ) process.exitCode = 1;
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
