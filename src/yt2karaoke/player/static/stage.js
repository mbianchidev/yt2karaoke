(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);

  if (document.body.dataset.view === "stage") {
    const video = byId("stage-video");
    let snapshot = null;
    let starting = false;
    const report = (error) => {
      console.error("Stage playback:", error);
      byId("stage-error").textContent = error.message;
      byId("stage-error").hidden = false;
    };
    const sync = () => {
      if (!snapshot) return;
      if (!window.opener || window.opener.closed) {
        video.pause();
        snapshot = null;
        byId("stage-countdown").hidden = true;
        byId("stage-idle").hidden = false;
        byId("stage-idle").textContent = "The studio closed. Open a new stage window from the studio to continue.";
        return;
      }
      const countdown = snapshot.countdown;
      byId("stage-countdown").hidden = !countdown;
      if (countdown) {
        byId("stage-next-singer").textContent = countdown.performer;
        byId("stage-next-song").textContent = countdown.title;
        byId("stage-countdown-label").textContent = countdown.label;
        byId("stage-seconds").textContent = countdown.waiting ? "--"
          : String(Math.max(0, Math.ceil((countdown.deadline - Date.now()) / 1000)));
      }
      if (video.readyState < 1 || !snapshot.src) return;
      const elapsed = snapshot.paused ? 0 : Math.max(0, Date.now() - snapshot.sentAt) / 1000;
      const expected = Math.min(snapshot.time + elapsed * snapshot.rate, video.duration || Infinity);
      if (Math.abs(video.currentTime - expected) > 0.1) video.currentTime = expected;
      video.playbackRate = snapshot.rate;
      if (snapshot.paused) video.pause();
      else if (video.paused && !starting) {
        const source = snapshot.src;
        starting = true;
        video.play().catch((error) => {
          if (snapshot?.src === source && !snapshot.paused && error.name !== "AbortError") report(error);
        }).finally(() => { starting = false; });
      }
    };
    window.addEventListener("message", (event) => {
      if (event.origin !== location.origin || event.source !== window.opener || event.data?.type !== "karaoke-stage") return;
      const next = event.data;
      if (next.src && new URL(next.src, location.href).origin !== location.origin) return;
      const changed = snapshot?.src !== next.src;
      snapshot = next;
      byId("stage-title").textContent = next.title || "Karaoke stage";
      video.hidden = !next.src;
      byId("stage-idle").hidden = Boolean(next.src || next.countdown);
      if (changed) {
        video.pause();
        video.muted = true;
        byId("stage-error").hidden = true;
        if (next.src) video.src = next.src;
        else video.removeAttribute("src");
        video.load();
      }
      sync();
    });
    video.addEventListener("loadedmetadata", sync);
    video.addEventListener("canplay", sync);
    video.addEventListener("error", () => {
      if (snapshot?.src) report(new Error("Stage video could not load. Close and reopen the stage window, or use the MP4 download."));
    });
    byId("stage-fullscreen").addEventListener("click", async () => {
      try {
        if (document.fullscreenElement) await document.exitFullscreen();
        else if (document.documentElement.requestFullscreen) await document.documentElement.requestFullscreen();
        else throw new Error("Full screen is unavailable in this browser. Maximize the stage window instead.");
      } catch (error) { report(error); }
    });
    document.addEventListener("fullscreenchange", () => {
      byId("stage-fullscreen").textContent = document.fullscreenElement ? "Exit full screen" : "Full screen";
    });
    byId("stage-close").addEventListener("click", () => window.close());
    const clock = setInterval(sync, 250);
    window.addEventListener("pagehide", () => {
      clearInterval(clock);
    });
    if (window.opener) window.opener.postMessage({ type: "karaoke-stage-ready" }, location.origin);
    else byId("stage-idle").textContent = "Open the stage window from the studio's Speakers & stage controls.";
    return;
  }

  window.KaraokeStage = class {
    constructor(video, { getCountdown, onError }) {
      this.video = video;
      this.getCountdown = getCountdown;
      this.onError = onError;
      this.receive = (event) => {
        if (event.origin !== location.origin || event.source !== this.popup) return;
        if (event.data?.type === "karaoke-stage-ready") this.sync();
      };
      window.addEventListener("message", this.receive);
      byId("stage-window-toggle").addEventListener("click", () => {
        if (this.popup && !this.popup.closed) this.close(); else this.open();
      });
      byId("find-displays").hidden = typeof window.getScreenDetails !== "function";
      byId("find-displays").addEventListener("click", () => this.findDisplays().catch(onError));
      byId("stage-display").addEventListener("change", () => {
        if (this.popup && !this.popup.closed) this.placeWindow();
      });
      this.clock = setInterval(() => {
        if (this.popup?.closed) this.closed();
        else this.sync();
      }, 250);
      ["play", "pause", "seeking", "seeked", "waiting", "playing", "ended", "loadedmetadata", "emptied"]
        .forEach((event) => video.addEventListener(event, () => this.sync()));
    }

    sync() {
      if (!this.popup || this.popup.closed) return;
      this.popup.postMessage({
        type: "karaoke-stage",
        src: this.video.getAttribute("src") || "",
        time: this.video.currentTime,
        rate: this.video.playbackRate,
        paused: this.video.paused || this.video.ended || this.video.readyState < 3,
        title: byId("now-playing-title").textContent,
        countdown: this.getCountdown(),
        sentAt: Date.now(),
      }, location.origin);
    }

    open() {
      const url = document.querySelector(".stage-output-controls").dataset.stageUrl;
      this.popup = window.open(url, "_blank", "popup,width=1120,height=700");
      if (!this.popup) {
        this.onError(new Error("The stage window was blocked. Allow pop-ups for this studio and try again."));
        return;
      }
      byId("stage-window-toggle").textContent = "Close stage window";
      this.placeWindow();
    }

    close() {
      this.popup?.close();
      this.closed();
    }

    closed() {
      this.popup = null;
      byId("stage-window-toggle").textContent = "Open stage window";
    }

    async findDisplays() {
      try {
        const details = await window.getScreenDetails();
        this.screens = details.screens;
        const select = byId("stage-display");
        select.replaceChildren(...this.screens.map((screen, index) => {
          const option = new Option(screen.label || `Display ${index + 1}`, String(index));
          option.selected = screen === details.currentScreen;
          return option;
        }));
        byId("stage-display-field").hidden = false;
      } catch (error) {
        throw new Error(`Displays could not be listed. Allow window-management access, or move the stage window manually. ${error.message}`);
      }
    }

    placeWindow() {
      const screen = this.screens?.[Number(byId("stage-display").value)];
      if (!screen || !this.popup) return;
      try {
        this.popup.moveTo(screen.availLeft, screen.availTop);
        this.popup.resizeTo(Math.min(1120, screen.availWidth), Math.min(700, screen.availHeight));
      } catch (error) {
        this.onError(new Error(`The stage window could not move. Drag it to your chosen display. ${error.message}`));
      }
    }

    destroy() {
      clearInterval(this.clock);
      window.removeEventListener("message", this.receive);
      this.close();
    }
  };
})();
