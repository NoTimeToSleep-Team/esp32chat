// Photo avatars: upload in account, persistence, avatar in chat, validation.
// Run: node tests/ui/avatar_check.js
const fs = require("fs");
const os = require("os");
const path = require("path");
const { SHOTS, check, summary, launch, login } = require("./lib");

const PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

(async () => {
  const pngPath = path.join(os.tmpdir(), "lc_avatar_test.png");
  const txtPath = path.join(os.tmpdir(), "lc_avatar_test.txt");
  fs.writeFileSync(pngPath, Buffer.from(PNG_B64, "base64"));
  fs.writeFileSync(txtPath, "not an image");

  const { browser, page } = await launch({ viewport: { width: 1280, height: 800 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  await login(page, "admin", "7428");

  await page.evaluate(() => { window.location.hash = "#/account"; });
  await page.waitForTimeout(2000);
  check("upload button on account page", await page.isVisible("#avatar-upload"));
  check("avatar hint shown", ((await page.textContent(".ava-hint")) || "").length > 10, await page.textContent(".ava-hint"));

  // wrong file type -> readable error, nothing breaks
  await page.setInputFiles("#avatar-file", txtPath);
  await page.waitForTimeout(900);
  const badToast = await page.evaluate(() => {
    const t = document.querySelector(".toast");
    return t ? t.textContent : "";
  });
  check("wrong file type rejected with message", /PNG|JPEG|WEBP/.test(badToast), badToast);

  // valid photo upload
  await page.setInputFiles("#avatar-file", pngPath);
  await page.waitForTimeout(3000);
  const uploaded = await page.evaluate(() => {
    const img = document.querySelector("#acct-avatar img");
    return { hasImg: !!img, src: img ? img.getAttribute("src") : "", toast: (document.querySelector(".toast") || {}).textContent || "" };
  });
  check("photo avatar set after upload", uploaded.hasImg && uploaded.src.indexOf("/account/api/profile/avatar") >= 0, JSON.stringify(uploaded));
  await page.screenshot({ path: SHOTS + "avatar-account.png" });

  // persistence after reload
  await page.reload({ waitUntil: "load" });
  await page.waitForTimeout(2500);
  await page.evaluate(() => { window.location.hash = "#/account"; });
  await page.waitForTimeout(2000);
  const persisted = await page.evaluate(() => !!document.querySelector("#acct-avatar img"));
  check("photo avatar persists after reload", persisted);

  // avatar in chat messages (lazy loaded)
  await page.evaluate(() => { window.location.hash = "#/chat"; });
  await page.waitForTimeout(2000);
  const items = await page.$$("#chat-list .chat-item");
  check("chat list has items", items.length > 0, "n=" + items.length);
  if (items.length) {
    await items[0].click();
    await page.waitForTimeout(3000);
    const chatAva = await page.evaluate(() => {
      const imgs = document.querySelectorAll("#msg-list .msg-avatar img");
      return { n: imgs.length, src: imgs.length ? imgs[0].getAttribute("src") : "" };
    });
    check("photo shown in chat message avatars", chatAva.n > 0 && chatAva.src.indexOf("/account/api/profile/avatar") >= 0, JSON.stringify(chatAva));
    await page.screenshot({ path: SHOTS + "avatar-chat.png" });
  }

  check("no page errors", errs.length === 0, errs.join(" | "));
  await browser.close();
  process.exit(summary());
})().catch(e => { console.error("ERR", e.message); process.exit(1); });
