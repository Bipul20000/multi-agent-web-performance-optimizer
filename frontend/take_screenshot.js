const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch();
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });
  await page.goto('http://localhost:3000/dashboard', { waitUntil: 'networkidle2' });
  
  // Click the "New Optimization" button
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const btn = buttons.find(b => b.textContent && b.textContent.includes('New Optimization'));
    if (btn) btn.click();
  });
  
  // Wait a moment for modal animation
  await new Promise(r => setTimeout(r, 1000));
  
  await page.screenshot({ path: '/Users/bipulkumar/.gemini/antigravity/brain/3eb49b58-59a5-41a3-a05a-ce124c4ddf01/dashboard_screenshot.png' });
  await browser.close();
  console.log('Screenshot taken!');
})();
