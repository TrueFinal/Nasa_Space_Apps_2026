import {test,expect} from '@playwright/test';
test('all five observed targets load, animate, subtract, measure and export',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/');await expect(page.locator('#source-badge')).toHaveText('EXEMPLO OBSERVADO');
 for(const [id,name] of [['barnard','Estrela de Barnard'],['epsilon','Epsilon Indi B'],['rwaur','RW Aurigae'],['rdra','R Draconis'],['wise0855','WISE 0855']]){
  await page.locator(`[data-id="${id}"]`).click();await expect(page.locator('#target-title')).toHaveText(name);await expect(page.locator('#frame-label')).not.toHaveText('1 / 1');
 }
 await expect(page.locator('#palette')).toHaveValue('inferno');await page.locator('#palette').selectOption('gray');await page.locator('#palette').selectOption('inferno');
 await page.locator('#play').click();await expect(page.locator('#frame-label')).not.toHaveText('1 / 5');await page.locator('#play').click();
 await page.locator('[data-mode="difference"]').click();await page.locator('#sky').click();await expect(page.locator('#spectrum-note')).toContainText('medidas');
 const gif=page.waitForEvent('download');await page.locator('#gif').click();expect((await gif).suggestedFilename()).toBe('spherex-temporal.gif');
 const csv=page.waitForEvent('download');await page.locator('#export-spectrum').click();expect((await csv).suggestedFilename()).toBe('spherex-spectrum.csv');
 expect(errors).toEqual([]);
});
test('mobile layout fits viewport and invalid coordinates are handled',async({page})=>{
 await page.setViewportSize({width:390,height:844});await page.goto('/');await expect(page.locator('#source-badge')).toHaveText('EXEMPLO OBSERVADO');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);
 await page.locator('#ra').fill('999');await page.locator('#search-button').click();await expect(page.locator('#status')).toContainText('0–360');
});
