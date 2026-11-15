import {test,expect} from '@playwright/test';

test('five real targets animate, stack, subtract, measure and export',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/lab');await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
 for(const [id,name,count] of [['barnard','Barnard’s Star',10],['epsilon','Epsilon Indi B',15],['wise0855','WISE 0855',12],['rwaur','RW Aurigae',6],['rdra','R Draconis',9]]){
  await page.locator(`[data-id="${id}"]`).click();
  await expect(page.locator('#target-title')).toHaveText(name);
  await expect(page.locator('#frame-label')).toContainText(` / ${count}`);
  const first=await page.locator('#frame-label').textContent();
  await expect(page.locator('#frame-label')).not.toHaveText(first);
  await page.locator('#by-frame').click();
  await page.locator('#stack-count').fill('3');await page.locator('#apply-stack').click();
  await expect(page.locator('[data-mode="trail"]')).toHaveClass(/active/);
  await page.locator('[data-mode="difference"]').click();
  await page.locator('#sky').click();await expect(page.locator('#spectrum-note')).toContainText('aperture measurements');
  await page.locator('[data-mode="image"]').click();
  const gif=page.waitForEvent('download');await page.locator('#gif').click();expect((await gif).suggestedFilename()).toBe('spherex-temporal.gif');
 }
 await expect(page.locator('#palette')).toHaveValue('gray');await expect(page.locator('#invert')).toBeChecked();
 const csv=page.waitForEvent('download');await page.locator('#export-spectrum').click();expect((await csv).suggestedFilename()).toBe('spherex-spectrum.csv');
 expect(errors).toEqual([]);
});

test('mobile layout and navigation fit, invalid coordinates are explained',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/lab');await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('#nav-toggle').click();await expect(page.locator('#navigation')).toBeVisible();
 await page.locator('#ra').fill('999');await page.locator('#search-button').click();await expect(page.locator('#status')).toContainText('0–360');
});

test('coordinate URL includes dates and live search forwards filters without replacing prior data',async({page})=>{
 await page.goto('/lab');await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
 let queried;
 await page.route('**/api/archive?**',async route=>{
  queried=new URL(route.request().url());
  await route.fulfill({status:200,contentType:'text/csv',body:'obs_id,access_url,energy_bandpassname,t_min\n'});
 });
 await page.locator('#ra').fill('08h55m10.831s');await page.locator('#dec').fill('-07:14:42.53');
 await page.locator('#start').fill('2025-05-01');await page.locator('#end').fill('2026-05-31');
 await page.locator('#collection').selectOption('spherex_dr1');
 await page.locator('#search-button').click();await expect(page.locator('#status')).toContainText('No exposures available');
 expect(Number(queried.searchParams.get('ra'))).toBeCloseTo(133.7951291667,8);
 expect(queried.searchParams.get('start')).toBe('2025-05-01');expect(queried.searchParams.get('end')).toBe('2026-05-31');
 await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
});

test('invalid coordinate links show an actionable message without crashing',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/lab?ra=999&dec=0');await expect(page.locator('#status')).toContainText('0–360');
 expect(errors).toEqual([]);
});

test('contextual glossary works with hover, keyboard and touch without changing the view',async({page,browser})=>{
 await page.goto('/lab');await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
 await expect(page.locator('.term-help')).toHaveCount(10);
 await expect(page.getByRole('button',{name:'Explain CSV',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Explain Download selection',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Explain Mean stack',exact:true})).toBeVisible();
 await expect(page.getByRole('button',{name:'Explain Difference image',exact:true})).toBeVisible();
 const help=page.getByRole('button',{name:'Explain Right Ascension (RA)',exact:true});
 expect(await help.evaluate(e=>e.getBoundingClientRect().width)).toBeLessThanOrEqual(16);
 const tip=page.locator('#glossary-ra');
 await help.hover();await expect(tip).toBeVisible();await expect(tip).toContainText('east–west coordinate');
 await page.keyboard.press('Escape');await expect(tip).toBeHidden();
 await help.focus();await expect(tip).toBeVisible();
 await page.keyboard.press('Escape');await expect(tip).toBeHidden();
 await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
 const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
 const phone=await context.newPage();await phone.goto('/lab');
 const button=phone.getByRole('button',{name:'Explain Motion trail',exact:true});
 await button.tap();const popup=phone.locator('#glossary-datamodetrail');await expect(popup).toBeVisible();
 await expect(popup).toContainText('does not draw or confirm a path');
 const box=await popup.boundingBox();expect(box.x).toBeGreaterThanOrEqual(0);expect(box.x+box.width).toBeLessThanOrEqual(390);
 await button.tap();await expect(popup).toBeHidden();
 await button.tap();await expect(popup).toBeVisible();
 await phone.locator('#target-title').tap();await expect(popup).toBeHidden();
 expect(await phone.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await context.close();
});

test('Zephyr logo loads and returns to the initial view without a self navigation link',async({page})=>{
 await page.goto('/lab');await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
 await expect(page.locator('#navigation a')).toHaveCount(1);
 await expect(page.locator('#navigation')).not.toContainText('Sky explorer');
 await expect(page.locator('.brand img')).toHaveAttribute('alt','Zephyr');
 await expect.poll(()=>page.locator('.brand img').evaluate(im=>im.complete&&im.naturalWidth>0)).toBe(true);
 await page.locator('[data-id="barnard"]').click();await expect(page.locator('#target-title')).toHaveText('Barnard’s Star');
 await page.locator('.brand').click();await expect(page).toHaveURL(/\/$/);
 await expect(page.locator('#hero')).toBeVisible();
 await page.locator('nav a[href="/lab"]').click();await expect(page.locator('#target-title')).toHaveText('WISE 0855');
});
