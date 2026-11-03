const ENDPOINT = "http://127.0.0.1:8765/tabs";
async function sendTabs() {
  try {
    const tabs = await chrome.tabs.query({});
    const payload = {
      browser: navigator.userAgent.includes("Firefox") ? "Firefox" :
        (navigator.userAgent.includes("Edg/") ? "Edge" :
        (navigator.userAgent.includes("OPR/") ? "Opera" : "Chromium")),
      tabs: tabs.filter(t => t.url && /^https?:\/\//i.test(t.url)).map(t => ({
        id: t.id, windowId: t.windowId, url: t.url, title: t.title || "", active: !!t.active
      }))
    };
    await fetch(ENDPOINT, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload)
    });
  } catch (_) {
    // Observer may be closed; retry on the next alarm.
  }
}
chrome.runtime.onInstalled.addListener(() => {
  chrome.alarms.create("gigaam-tabs", {periodInMinutes: 1});
  sendTabs();
});
chrome.runtime.onStartup.addListener(sendTabs);
chrome.alarms.onAlarm.addListener(sendTabs);
chrome.tabs.onActivated.addListener(sendTabs);
chrome.tabs.onCreated.addListener(sendTabs);
chrome.tabs.onRemoved.addListener(sendTabs);
chrome.tabs.onUpdated.addListener((_id, change) => {
  if (change.url || change.title) sendTabs();
});
