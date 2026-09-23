// In-app support page (#/support): tickets, thread, attachments, status, mobile views.
// Run: node tests/ui/support_spa_check.js
const fs = require("fs");
const os = require("os");
const path = require("path");
const { SHOTS, check, summary, launch, login } = require("./lib");

const PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

(async () => {
  const pngPath = path.join(os.tmpdir(), "lc_support_spa.png");
  fs.writeFileSync(pngPath, Buffer.from(PNG_B64, "base64"));

  const { browser, page } = await launch({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  await login(page, "admin", "7428");
  await page.evaluate(() => { window.location.hash = "#/support"; });
  await page.waitForTimeout(3000);

  const list = await page.evaluate(() => ({
    title: document.querySelector(".page-title")?.textContent,
    sub: document.querySelector(".page-subtitle")?.textContent || "",
    tickets: document.querySelectorAll(".ticket-item").length,
    selected: document.querySelectorAll(".ticket-item.selected").length,
    pill: document.querySelector(".ticket-item .ticket-status")?.textContent,
    thread: document.querySelector(".sup-thread-title")?.textContent,
    options: Array.from(document.querySelectorAll("#sup-status option")).map(o => o.textContent),
    bubbles: document.querySelectorAll(".sup-msgs .msg").length,
    overflowX: document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth
  }));
  check("russian page header", list.title === "Поддержка" && /поддержку/i.test(list.sub), JSON.stringify({ t: list.title, s: list.sub }));
  check("ticket list loaded and first selected", list.tickets > 0 && list.selected === 1 && !!list.thread, JSON.stringify(list));
  check("status shown in russian", ["Открыто", "В работе", "Решено", "Закрыто"].includes(list.pill), list.pill);
  check("status select has russian options", list.options.join(",") === "Открыто,В работе,Решено,Закрыто", list.options.join(","));
  check("thread bubbles rendered", list.bubbles >= 1, "n=" + list.bubbles);
  await page.screenshot({ path: SHOTS + "support-spa-desktop.png" });

  // new ticket with an attachment
  const title = "UI SPA " + Math.random().toString(36).slice(2, 8);
  await page.click("#new-ticket-btn");
  await page.waitForTimeout(500);
  const modal = await page.evaluate(() => ({
    heading: document.querySelector("#new-ticket-modal h3")?.textContent,
    attach: !!document.querySelector("#ticket-attach")
  }));
  check("new ticket modal is localized with attach button", modal.heading === "Новое обращение" && modal.attach, JSON.stringify(modal));
  await page.fill("#ticket-title", title);
  await page.fill("#ticket-body", "Проверка встроенной страницы поддержки.");
  await page.setInputFiles("#ticket-file", pngPath);
  await page.waitForTimeout(1600);
  const chip = await page.evaluate(() => ({ hidden: document.getElementById("ticket-chips").hidden, text: document.getElementById("ticket-chips").textContent.trim() }));
  check("attachment chip in the modal", !chip.hidden && chip.text.length > 0, JSON.stringify(chip));
  await page.click("#ticket-submit");
  await page.waitForTimeout(3000);
  const created = await page.evaluate(() => ({
    thread: document.querySelector(".sup-thread-title")?.textContent,
    selectedTitle: document.querySelector(".ticket-item.selected .ticket-item-title")?.textContent,
    img: !!document.querySelector(".sup-msgs .msg .attachment.image img")
  }));
  check("ticket created and selected", created.thread === title && created.selectedTitle === title, JSON.stringify(created));
  check("attachment image in the created message", created.img, JSON.stringify(created));

  // reply with an attachment
  await page.setInputFiles("#support-file", pngPath);
  await page.waitForTimeout(1600);
  const replyChip = await page.evaluate(() => !document.getElementById("support-chips").hidden);
  check("attachment chip in the composer", replyChip);
  await page.fill("#support-input", "Ответ из встроенной поддержки.");
  await page.click("#support-send");
  await page.waitForTimeout(2500);
  const replied = await page.evaluate(() => {
    const msgs = document.querySelectorAll(".sup-msgs .msg");
    const last = msgs[msgs.length - 1];
    return {
      count: msgs.length,
      own: last ? last.classList.contains("out") : false,
      author: last ? last.querySelector(".msg-author").textContent : "",
      text: last ? last.querySelector(".msg-text").textContent : "",
      img: last ? !!last.querySelector(".attachment.image img") : false
    };
  });
  check("reply sent as own bubble with attachment", replied.own && replied.author === "Вы" && replied.text === "Ответ из встроенной поддержки." && replied.img, JSON.stringify(replied));

  // status change from the select
  await page.selectOption("#sup-status", "resolved");
  await page.waitForTimeout(2500);
  const status = await page.evaluate(() => ({
    toast: (document.querySelector(".toast") || {}).textContent || "",
    pill: document.querySelector(".ticket-item.selected .ticket-status")?.textContent,
    select: document.getElementById("sup-status")?.value
  }));
  check("status changed to resolved", status.pill === "Решено" && status.select === "resolved", JSON.stringify(status));

  // mobile: list -> thread -> back
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => document.body.classList.remove("sup-thread"));
  await page.waitForTimeout(700);
  const mobileList = await page.evaluate(() => ({
    listVisible: getComputedStyle(document.querySelector(".sup-side")).display !== "none",
    detailVisible: getComputedStyle(document.getElementById("ticket-detail")).display !== "none",
    overflowX: document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth
  }));
  check("mobile shows the list only", mobileList.listVisible && !mobileList.detailVisible, JSON.stringify(mobileList));
  check("no horizontal overflow on mobile", mobileList.overflowX <= 2, "overflowX=" + mobileList.overflowX);
  await page.screenshot({ path: SHOTS + "support-spa-mobile-list.png" });

  await page.evaluate(() => document.querySelector(".ticket-item").click());
  await page.waitForTimeout(2500);
  const mobileThread = await page.evaluate(() => ({
    open: document.body.classList.contains("sup-thread"),
    back: getComputedStyle(document.getElementById("sup-back")).display !== "none",
    listHidden: getComputedStyle(document.querySelector(".sup-side")).display === "none",
    composer: !!document.querySelector("#support-input")?.offsetParent,
    overflowX: document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth
  }));
  check("tapping a ticket opens the thread on mobile", mobileThread.open && mobileThread.back && mobileThread.listHidden && mobileThread.composer, JSON.stringify(mobileThread));
  check("no horizontal overflow in the mobile thread", mobileThread.overflowX <= 2, "overflowX=" + mobileThread.overflowX);
  await page.screenshot({ path: SHOTS + "support-spa-mobile-thread.png" });

  await page.click("#sup-back");
  await page.waitForTimeout(700);
  const back = await page.evaluate(() => ({
    open: document.body.classList.contains("sup-thread"),
    listVisible: getComputedStyle(document.querySelector(".sup-side")).display !== "none"
  }));
  check("back returns to the ticket list", !back.open && back.listVisible, JSON.stringify(back));

  check("no page errors", errs.length === 0, errs.join(" | "));
  await browser.close();
  process.exit(summary());
})().catch(e => { console.error("ERR", e.message); process.exit(1); });
