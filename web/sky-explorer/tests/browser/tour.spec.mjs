import {test,expect} from '@playwright/test';

test('merged onboarding can be dismissed, replayed and finished without blocking the lab',async({page})=>{
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 await page.goto('/lab');
 await expect(page.locator('#tour-welcome-title')).toBeVisible();
 await page.getByRole('button',{name:"No thanks, I'll explore on my own"}).click();
 await expect(page.locator('.tour-welcome')).toHaveCount(0);
 await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
 await page.locator('#tour-start').click();
 for(let n=1;n<=4;n++){
  await expect(page.locator('.tour-eyebrow')).toHaveText(`STEP ${n} OF 4`);
  await page.locator('.tour-next').click();
 }
 await expect(page.locator('.tour-bubble')).toHaveCount(0);
 await page.locator('[data-id="barnard"]').click();await expect(page.locator('#target-title')).toHaveText('Barnard’s Star');
 await page.reload();await expect(page.locator('#source-badge')).toHaveText('SAVED REAL OBSERVATIONS');
 await expect(page.locator('.tour-welcome')).toHaveCount(0);
 expect(errors).toEqual([]);
});
