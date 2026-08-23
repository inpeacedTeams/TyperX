(() => {
  let lastText = "";
  let timer = null;

  const collect = () => {
    const words = [...document.querySelectorAll("#words .word")]
      .map((word) => word.textContent?.trim() ?? "")
      .filter(Boolean);
    return words.join(" ");
  };

  const send = async () => {
    const text = collect();
    if (!text || text === lastText) return;
    try {
      await fetch("http://127.0.0.1:8765/monkeytype", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      lastText = text;
    } catch {
      // TyperX is not listening yet. Retry while the test is visible.
    }
  };

  const schedule = () => {
    clearTimeout(timer);
    timer = setTimeout(send, 150);
  };

  new MutationObserver(schedule).observe(document.documentElement, {
    childList: true,
    subtree: true,
    characterData: true,
  });
  setInterval(send, 750);
  schedule();
})();
