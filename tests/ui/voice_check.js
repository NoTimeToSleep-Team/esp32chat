// Voice messages: record button, recording bar, preview, upload, playback.
// Uses Chrome fake media devices (localhost is a secure context).
// Run: node tests/ui/voice_check.js
const fs = require("fs");
const os = require("os");
const path = require("path");
const { chromium, SHOTS, check, summary, login } = require("./lib");

const FAKE_MEDIA_ARGS = ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"];

(async () => {
  // ---------- 1. recording works (fake mic, secure context = localhost) ----------
  const browser = await chromium.launch({ channel: "msedge", headless: true, args: FAKE_MEDIA_ARGS });
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 800 }, permissions: ["microphone"] });
  const page = await ctx.newPage();
  const errs = [];
  page.on("pageerror", e => errs.push(e.message));
  await login(page, "admin", "7428");
  const items = await page.$$("#chat-list .chat-item");
  check("chat list has items", items.length > 0, "n=" + items.length);
  await items[0].click();
  await page.waitForTimeout(1200);

  check("mic button in composer", await page.isVisible("#mic-btn"));
  const secure = await page.evaluate(() => window.isSecureContext);
  check("localhost is a secure context", secure === true);

  await page.click("#mic-btn");
  await page.waitForTimeout(1600);
  const recState = await page.evaluate(() => ({
    barVisible: !document.querySelector("#voice-rec").classList.contains("hidden"),
    timer: document.querySelector("#voice-timer").textContent,
    micHot: document.querySelector("#mic-btn").classList.contains("recording")
  }));
  check("recording bar visible", recState.barVisible, JSON.stringify(recState));
  check("mic button in recording state", recState.micHot, JSON.stringify(recState));
  check("timer counts up", recState.timer !== "0:00", recState.timer);
  await page.screenshot({ path: SHOTS + "voice-recording.png" });

  await page.click("#voice-stop");
  await page.waitForTimeout(1200);
  const preview = await page.evaluate(() => ({
    barHidden: document.querySelector("#voice-rec").classList.contains("hidden"),
    chips: document.querySelectorAll(".attach-chip.voice").length,
    player: !!document.querySelector(".attach-chip.voice audio"),
    size: (document.querySelector(".attach-chip.voice .attach-size") || {}).textContent || ""
  }));
  check("recording bar hidden after stop", preview.barHidden, JSON.stringify(preview));
  check("voice chip with player appears", preview.chips === 1 && preview.player, JSON.stringify(preview));
  check("recorded file has size", /\d/.test(preview.size), preview.size);
  await page.screenshot({ path: SHOTS + "voice-preview.png" });

  await page.click("#send-btn");
  await page.waitForTimeout(3500);
  const sent = await page.evaluate(() => {
    const msgs = document.querySelectorAll("#msg-list .msg");
    const last = msgs[msgs.length - 1];
    if (!last) return null;
    const audio = last.querySelector(".attachment.audio audio");
    return { hasAudio: !!audio, src: audio ? String(audio.getAttribute("src")).slice(0, 60) : "", chips: document.querySelectorAll(".attach-chip.voice").length };
  });
  check("voice message sent and rendered as player", sent && sent.hasAudio, JSON.stringify(sent));
  check("preview cleared after send", sent && sent.chips === 0, JSON.stringify(sent));

  await page.click("#mic-btn");
  await page.waitForTimeout(1200);
  await page.click("#voice-cancel");
  await page.waitForTimeout(800);
  const cancelled = await page.evaluate(() => ({
    barHidden: document.querySelector("#voice-rec").classList.contains("hidden"),
    chips: document.querySelectorAll(".attach-chip.voice").length
  }));
  check("cancel discards recording", cancelled.barHidden && cancelled.chips === 0, JSON.stringify(cancelled));
  check("no page errors (recording)", errs.length === 0, errs.join(" | "));
  await page.close();

  // ---------- 2. no mediaDevices -> clear message, no crash ----------
  const ctx2 = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  const page2 = await ctx2.newPage();
  const errs2 = [];
  page2.on("pageerror", e => errs2.push(e.message));
  await page2.addInitScript(() => {
    Object.defineProperty(navigator, "mediaDevices", { get: () => undefined, configurable: true });
  });
  await login(page2, "admin", "7428");
  const items2 = await page2.$$("#chat-list .chat-item");
  await items2[0].click();
  await page2.waitForTimeout(1200);
  await page2.click("#mic-btn");
  await page2.waitForTimeout(900);
  const noMic = await page2.evaluate(() => {
    const toast = document.querySelector(".toast");
    return { toast: toast ? toast.textContent.slice(0, 90) : "", bar: !document.querySelector("#voice-rec").classList.contains("hidden") };
  });
  check("no-HTTPS/no-mic path shows clear message", noMic.toast.length > 10 && !noMic.bar, JSON.stringify(noMic));
  check("no page errors (no-mic path)", errs2.length === 0, errs2.join(" | "));
  await page2.screenshot({ path: SHOTS + "voice-no-mic.png" });
  await page2.close();

  // ---------- 3. audio file upload renders as a player ----------
  const ctx3 = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page3 = await ctx3.newPage();
  const wavPath = path.join(os.tmpdir(), "lc_voice_test.wav");
  const samples = 2400; // 0.3s of silence, 8 kHz mono 16-bit
  const buf = Buffer.alloc(44 + samples * 2);
  buf.write("RIFF", 0); buf.writeUInt32LE(36 + samples * 2, 4); buf.write("WAVE", 8);
  buf.write("fmt ", 12); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22);
  buf.writeUInt32LE(8000, 24); buf.writeUInt32LE(16000, 28); buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34);
  buf.write("data", 36); buf.writeUInt32LE(samples * 2, 40);
  fs.writeFileSync(wavPath, buf);
  await login(page3, "admin", "7428");
  const items3 = await page3.$$("#chat-list .chat-item");
  await items3[0].click();
  await page3.waitForTimeout(1200);
  await page3.setInputFiles("#msg-file", wavPath);
  await page3.waitForTimeout(800);
  check("uploaded audio shows a chip player", await page3.evaluate(() => !!document.querySelector(".attach-chip.voice audio")));
  await page3.click("#send-btn");
  await page3.waitForTimeout(3000);
  const uploaded = await page3.evaluate(() => {
    const msgs = document.querySelectorAll("#msg-list .msg");
    const last = msgs[msgs.length - 1];
    return last ? !!last.querySelector(".attachment.audio audio") : false;
  });
  check("uploaded audio message renders as player", uploaded);
  await page3.close();

  await browser.close();
  process.exit(summary());
})().catch(e => { console.error("ERR", e.message); process.exit(1); });
