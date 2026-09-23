// Support page (/support): auto-load, ticket flow, attachments, mobile view.
// Run: node tests/ui/support_check.js
const fs = require("fs");
const os = require("os");
const path = require("path");
const { SHOTS, check, summary, launch, login } = require("./lib");

const PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

(async () => {
  const pngPath = path.join(os.tmpdir(), "lc_support_test.png");
  fs.writeFileSync(pngPath, Buffer.from(PNG_B64, "base64"));

  const { browser, page } = await launch({ viewport: { width: 1280, height: 900 } });
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));

  await login(page, "admin", "7428");
  await page.goto(page.url().split("#")[0].replace(/\/$/, "") + "/support", { waitUntil: "load" });
  await page.waitForTimeout(2500);

  check("nav with a way back to the app", await page.isVisible(".nav-links a[href='/#/chat']"));
  check("page title", (await page.textContent("h1")) === "Поддержка", await page.textContent("h1"));
  const loaded = await page.evaluate(() => ({
    hint: document.getElementById("replyHint").textContent,
    tickets: document.querySelectorAll("#ticketList .ticket-btn").length,
    threadTitle: document.getElementById("activeTicketTitle").textContent
  }));
  check("tickets auto-load without pressing a button", loaded.tickets > 0 && !/Укажите session token/.test(loaded.hint), JSON.stringify(loaded));
  check("first ticket opens automatically", loaded.threadTitle && loaded.threadTitle !== "Выберите обращение", loaded.threadTitle);
  await page.screenshot({ path: SHOTS + "support-desktop.png" });

  // new ticket
  const title = "UI тест " + Math.random().toString(36).slice(2, 8);
  await page.fill("#ticketTitle", title);
  await page.fill("#ticketBody", "Проверка страницы поддержки: создание обращения.");
  await page.click("#createTicketBtn");
  await page.waitForTimeout(2500);
  const created = await page.evaluate(() => ({
    title: document.getElementById("activeTicketTitle").textContent,
    pill: document.getElementById("threadStatusPill").textContent,
    messages: document.querySelectorAll("#messagesViewport .msg").length,
    mine: document.querySelectorAll("#messagesViewport .msg.own").length
  }));
  check("ticket created and selected", created.title === title, JSON.stringify(created) + " expected " + title);
  check("status pill shows a russian label", ["Открыто", "В работе", "Решено", "Закрыто"].includes(created.pill), created.pill);
  check("first message rendered as own", created.messages >= 1 && created.mine >= 1, JSON.stringify(created));

  // reply with an attachment
  await page.setInputFiles("#filePicker", pngPath);
  await page.waitForTimeout(1500);
  const chip = await page.evaluate(() => {
    const box = document.getElementById("replyFiles");
    return { hidden: box.hidden, text: box.textContent.trim() };
  });
  check("attachment chip after upload", !chip.hidden && chip.text.length > 0, JSON.stringify(chip));

  await page.fill("#replyBody", "Ответ с вложением.");
  await page.click("#sendReplyBtn");
  await page.waitForTimeout(2500);
  const replied = await page.evaluate(() => {
    const msgs = document.querySelectorAll("#messagesViewport .msg");
    const last = msgs[msgs.length - 1];
    return {
      count: msgs.length,
      own: last ? last.classList.contains("own") : false,
      body: last ? last.querySelector(".body").textContent : "",
      img: last ? !!last.querySelector(".msg-atts img") : false,
      chipGone: document.getElementById("replyFiles").hidden
    };
  });
  check("reply sent with attachment", replied.count >= 2 && replied.own && replied.body === "Ответ с вложением." && replied.img && replied.chipGone, JSON.stringify(replied));

  // status update
  await page.selectOption("#statusSelect", "in_progress");
  await page.click("#updateStatusBtn");
  await page.waitForTimeout(2200);
  const status = await page.evaluate(() => ({
    pill: document.getElementById("threadStatusPill").textContent,
    hint: document.getElementById("replyHint").textContent
  }));
  check("status updated to in progress", status.pill === "В работе", JSON.stringify(status));

  // mobile: list first, thread replaces it, back returns
  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate(() => document.body.classList.remove("thread-open"));
  await page.waitForTimeout(600);
  const mobileList = await page.evaluate(() => {
    const se = document.scrollingElement;
    const thread = document.getElementById("threadCard");
    return {
      overflowX: se.scrollWidth - se.clientWidth,
      threadVisible: thread.getBoundingClientRect().width > 0 && getComputedStyle(thread).display !== "none",
      listVisible: getComputedStyle(document.querySelector(".col-left")).display !== "none"
    };
  });
  check("no horizontal overflow on mobile", mobileList.overflowX <= 2, "overflowX=" + mobileList.overflowX);
  check("mobile shows the ticket list only", mobileList.listVisible && !mobileList.threadVisible, JSON.stringify(mobileList));
  await page.screenshot({ path: SHOTS + "support-mobile-list.png" });

  await page.evaluate(() => document.querySelector("#ticketList .ticket-btn").click());
  await page.waitForTimeout(2000);
  const mobileThread = await page.evaluate(() => {
    const thread = document.getElementById("threadCard");
    return {
      open: document.body.classList.contains("thread-open"),
      threadVisible: getComputedStyle(thread).display !== "none",
      listHidden: getComputedStyle(document.querySelector(".col-left")).display === "none",
      backVisible: getComputedStyle(document.getElementById("backBtn")).display !== "none",
      overflowX: document.scrollingElement.scrollWidth - document.scrollingElement.clientWidth
    };
  });
  check("tapping a ticket opens the thread on mobile", mobileThread.open && mobileThread.threadVisible && mobileThread.listHidden && mobileThread.backVisible, JSON.stringify(mobileThread));
  check("no horizontal overflow in the thread", mobileThread.overflowX <= 2, "overflowX=" + mobileThread.overflowX);
  await page.screenshot({ path: SHOTS + "support-mobile-thread.png" });

  await page.click("#backBtn");
  await page.waitForTimeout(700);
  const back = await page.evaluate(() => ({
    open: document.body.classList.contains("thread-open"),
    listVisible: getComputedStyle(document.querySelector(".col-left")).display !== "none"
  }));
  check("back returns to the ticket list", !back.open && back.listVisible, JSON.stringify(back));

  check("no page errors", errs.length === 0, errs.join(" | "));
  await browser.close();
  process.exit(summary());
})().catch(e => { console.error("ERR", e.message); process.exit(1); });
