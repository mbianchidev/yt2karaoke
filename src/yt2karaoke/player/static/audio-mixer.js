(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const workletUrl = new URL("pitch-processor.js", document.currentScript.src).href;
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;

  window.KaraokeAudio = class {
    constructor(video, { onError, onNotice }) {
      this.video = video;
      this.vocals = byId("original-vocals");
      this.onError = onError;
      this.onNotice = onNotice;
      this.masterLevel = Number(byId("volume-input").value) / 100;
      this.vocalLevel = 0;
      this.micRequest = 0;
      this.sourceVersion = 0;
      this.outputId = "";
      this.inputId = "";
      video.volume = this.masterLevel;
      this.bindControls();
      ["playing", "seeked", "ratechange"].forEach((event) => {
        video.addEventListener(event, () => this.syncVocals());
      });
      ["pause", "waiting", "seeking", "ended", "emptied"].forEach((event) => {
        video.addEventListener(event, () => this.vocals.pause());
      });
      video.addEventListener("timeupdate", () => {
        if (!this.vocals.paused && Math.abs(this.vocals.currentTime - video.currentTime) > 0.06) {
          this.vocals.currentTime = video.currentTime;
        }
        if (this.vocals.paused && !video.paused && this.vocalLevel > 0) this.syncVocals();
      });
      this.vocals.addEventListener("canplay", () => this.syncVocals());
      this.vocals.addEventListener("error", () => {
        if (!this.vocals.getAttribute("src")) return;
        this.video.pause();
        this.onError(new Error("Original vocals could not load. Refresh the queue, or choose 0% to play the instrumental."));
      });
      this.deviceChange = () => this.refreshDevices(true).catch(onError);
      navigator.mediaDevices?.addEventListener("devicechange", this.deviceChange);
      this.refreshDevices().catch(onError);
    }

    async prepare() {
      if (this.disposed) throw new Error("The audio mixer is closed. Reload the studio to play again.");
      if (!AudioContextClass) return;
      if (!this.initializing) {
        this.initializing = Promise.resolve().then(() => {
          if (this.disposed) throw new Error("The audio mixer is closed. Reload the studio to play again.");
          this.context = new AudioContextClass({ latencyHint: "interactive" });
          this.backing = this.context.createGain();
          this.original = this.context.createGain();
          this.master = this.context.createGain();
          const limiter = this.context.createDynamicsCompressor();
          limiter.threshold.value = -1;
          limiter.knee.value = 0;
          limiter.ratio.value = 20;
          limiter.attack.value = 0.003;
          limiter.release.value = 0.08;
          this.videoSource = this.context.createMediaElementSource(this.video);
          this.vocalSource = this.context.createMediaElementSource(this.vocals);
          this.videoSource.connect(this.backing).connect(this.master);
          this.vocalSource.connect(this.original).connect(this.master);
          this.master.connect(limiter).connect(this.context.destination);
          this.video.volume = 1;
          this.vocals.volume = 1;
          this.backing.gain.value = Number(byId("backing-volume").value) / 100;
          this.original.gain.value = this.vocalLevel;
          this.master.gain.value = this.muted ? 0 : this.masterLevel;
        });
      }
      await this.initializing;
    }

    async resume() {
      await this.prepare();
      if (this.context?.state === "suspended") await this.context.resume();
    }

    ramp(parameter, value) {
      parameter.setTargetAtTime(value, this.context.currentTime, 0.015);
    }

    setSong(url) {
      if ((this.vocals.getAttribute("src") || null) === (url || null)) return;
      ++this.sourceVersion;
      this.vocals.pause();
      if (url) this.vocals.src = url;
      else this.vocals.removeAttribute("src");
      this.vocals.load();
    }

    async setVocalLevel(level) {
      this.vocalLevel = level;
      if (level && this.vocals.getAttribute("src")) {
        if (!AudioContextClass) throw new Error("Live vocal mixing needs a browser with Web Audio. You can still create a vocal export.");
        await this.prepare();
      }
      if (this.original) this.ramp(this.original.gain, this.vocalLevel);
      this.syncVocals();
    }

    async syncVocals() {
      const video = this.video;
      const shouldPlay = () => this.vocalLevel > 0 && this.vocals.getAttribute("src")
        && !video.paused && !video.ended && !video.seeking && video.readyState >= 3;
      if (!shouldPlay()) { this.vocals.pause(); return; }
      if (this.vocalStarting) return;
      const version = this.sourceVersion;
      this.vocalStarting = true;
      try {
        await this.resume();
        if (version !== this.sourceVersion || !shouldPlay()) return;
        if (this.vocals.readyState >= 1 && Math.abs(this.vocals.currentTime - video.currentTime) > 0.06) {
          this.vocals.currentTime = video.currentTime;
        }
        this.vocals.playbackRate = video.playbackRate;
        this.vocals.loop = video.loop;
        await this.vocals.play();
      } catch (error) {
        if (version !== this.sourceVersion || !shouldPlay() || error.name === "AbortError") return;
        video.pause();
        this.onError(new Error(`Original vocals could not play: ${error.message}`));
      } finally {
        this.vocalStarting = false;
      }
    }

    setMaster(level) {
      this.masterLevel = level;
      byId("volume-input").value = String(Math.round(level * 100));
      byId("speaker-volume").value = byId("volume-input").value;
      byId("speaker-volume-value").textContent = `${Math.round(level * 100)}%`;
      if (this.master) this.ramp(this.master.gain, this.muted ? 0 : level);
      else this.video.volume = this.muted ? 0 : level;
    }

    async refreshDevices(handleRemoval = false) {
      if (!navigator.mediaDevices?.enumerateDevices) return;
      const devices = await navigator.mediaDevices.enumerateDevices();
      for (const [id, kind, label] of [
        ["mic-device", "audioinput", "microphone"], ["speaker-device", "audiooutput", "speakers"],
      ]) {
        const select = byId(id);
        const selected = select.value;
        const options = [new Option(`System default ${label}`, "")];
        devices.filter((device) => device.kind === kind && device.deviceId && device.deviceId !== "default")
          .forEach((device, index) => options.push(new Option(device.label || `${label} ${index + 1}`, device.deviceId)));
        select.replaceChildren(...options);
        if (options.some((option) => option.value === selected)) select.value = selected;
        else if (handleRemoval && selected) {
          if (kind === "audioinput") {
            this.stopMicrophone();
            this.onError(new Error("The selected microphone disconnected. Choose a microphone and enable it again."));
          } else {
            await this.setOutput("");
            this.onNotice("The selected speakers disconnected. Audio now uses the system default.");
          }
        }
      }
    }

    async setOutput(id) {
      byId("speaker-device").disabled = true;
      byId("choose-speakers").disabled = true;
      try {
        await this.resume();
        if (!this.context?.setSinkId) throw new Error("Speaker selection is not supported here. Choose an output in your system sound settings.");
        await this.context.setSinkId(id);
        this.outputId = id;
        byId("speaker-device").value = id;
      } finally {
        byId("speaker-device").disabled = typeof AudioContextClass?.prototype.setSinkId !== "function";
        byId("choose-speakers").disabled = false;
      }
    }

    async startMicrophone() {
      const request = ++this.micRequest;
      const device = byId("mic-device").value;
      let stream;
      byId("mic-toggle").disabled = true;
      byId("mic-device").disabled = true;
      try {
        await this.resume();
        stream = await navigator.mediaDevices.getUserMedia({
          audio: {
            ...(device ? { deviceId: { exact: device } } : {}),
            channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: false,
          },
        });
        if (!this.workletReady) this.workletReady = this.context.audioWorklet.addModule(workletUrl);
        await this.workletReady;
        if (request !== this.micRequest || this.disposed) {
          stream.getTracks().forEach((track) => track.stop());
          return;
        }
        this.releaseMicrophone();
        const source = this.context.createMediaStreamSource(stream);
        const pitch = new AudioWorkletNode(this.context, "karaoke-pitch");
        const bass = this.context.createBiquadFilter();
        bass.type = "lowshelf";
        bass.frequency.value = 150;
        const mid = this.context.createBiquadFilter();
        mid.type = "peaking";
        mid.frequency.value = 1000;
        mid.Q.value = 0.7;
        const treble = this.context.createBiquadFilter();
        treble.type = "highshelf";
        treble.frequency.value = 4000;
        const compressor = this.context.createDynamicsCompressor();
        compressor.attack.value = 0.008;
        compressor.release.value = 0.2;
        const gain = this.context.createGain();
        gain.gain.value = 0;
        const analyser = this.context.createAnalyser();
        analyser.fftSize = 256;
        source.connect(pitch).connect(bass).connect(mid).connect(treble).connect(compressor).connect(gain).connect(this.master);
        source.connect(analyser);
        this.mic = { source, pitch, bass, mid, treble, compressor, gain, analyser };
        this.stream = stream;
        this.inputId = device;
        byId("mic-monitor").checked = false;
        byId("mic-monitor").disabled = false;
        byId("mic-toggle").textContent = "Disable microphone";
        byId("mic-status").textContent = "Microphone on / muted";
        this.updateEffects();
        pitch.addEventListener("processorerror", () => {
          this.stopMicrophone();
          this.onError(new Error("The voice effect stopped. Enable the microphone again to restart it."));
        });
        stream.getAudioTracks()[0].addEventListener("ended", () => {
          if (this.stream !== stream) return;
          this.stopMicrophone();
          this.onError(new Error("Microphone access ended. Check the device and browser permission, then enable it again."));
        });
        const samples = new Float32Array(analyser.fftSize);
        const meter = () => {
          if (this.stream !== stream) return;
          analyser.getFloatTimeDomainData(samples);
          byId("mic-meter").value = Math.sqrt(samples.reduce((sum, value) => sum + value * value, 0) / samples.length);
          this.meterFrame = requestAnimationFrame(meter);
        };
        meter();
        this.refreshDevices().catch((error) => {
          this.onError(new Error(`Audio devices could not be refreshed: ${error.message}`));
        });
      } catch (error) {
        if (stream && this.stream !== stream) stream.getTracks().forEach((track) => track.stop());
        if (request !== this.micRequest || this.disposed) return;
        byId("mic-device").value = this.inputId;
        this.workletReady = null;
        const hint = error.name === "NotAllowedError"
          ? "Allow microphone access in your browser and try again."
          : error.name === "NotFoundError" || error.name === "OverconstrainedError"
            ? "Choose an available microphone and try again." : error.message;
        this.onError(new Error(`Microphone could not start. ${hint}`));
      } finally {
        byId("mic-toggle").disabled = false;
        byId("mic-device").disabled = false;
      }
    }

    releaseMicrophone() {
      if (this.stream) this.stream.getTracks().forEach((track) => track.stop());
      this.stream = null;
      if (this.mic) this.mic.pitch.port.postMessage("stop");
      if (this.mic) Object.values(this.mic).forEach((node) => node.disconnect());
      this.mic = null;
      cancelAnimationFrame(this.meterFrame);
      byId("mic-meter").value = 0;
    }

    stopMicrophone() {
      ++this.micRequest;
      this.releaseMicrophone();
      byId("mic-monitor").checked = false;
      byId("mic-monitor").disabled = true;
      byId("mic-toggle").textContent = "Enable microphone";
      byId("mic-status").textContent = "Microphone off";
    }

    updateMonitor() {
      if (!this.mic) return;
      const monitoring = byId("mic-monitor").checked;
      this.ramp(this.mic.gain.gain, monitoring ? Number(byId("mic-volume").value) / 100 : 0);
      byId("mic-status").textContent = monitoring ? "Microphone on / monitoring" : "Microphone on / muted";
    }

    updateEffects() {
      const semitones = Number(byId("pitch-input").value);
      byId("pitch-value").textContent = `${semitones > 0 ? "+" : ""}${semitones} st`;
      byId("pitch-input").setAttribute("aria-valuetext", `${semitones} semitones`);
      document.querySelectorAll("[data-pitch]").forEach((button) => {
        button.setAttribute("aria-pressed", String(Number(button.dataset.pitch) === semitones));
      });
      for (const id of ["effect-mix", "compression", "mic-volume", "backing-volume"]) {
        byId(`${id}-value`).textContent = `${byId(id).value}%`;
      }
      for (const id of ["bass", "mid", "treble"]) {
        const value = Number(byId(`eq-${id}`).value);
        byId(`eq-${id}-value`).textContent = `${value > 0 ? "+" : ""}${value} dB`;
        if (this.mic) this.ramp(this.mic[id].gain, value);
      }
      if (this.backing) this.ramp(this.backing.gain, Number(byId("backing-volume").value) / 100);
      if (this.mic) {
        this.ramp(this.mic.pitch.parameters.get("semitones"), semitones);
        this.ramp(this.mic.pitch.parameters.get("mix"), Number(byId("effect-mix").value) / 100);
        const amount = Number(byId("compression").value) / 100;
        this.ramp(this.mic.compressor.threshold, amount ? -12 - 24 * amount : 0);
        this.ramp(this.mic.compressor.ratio, 1 + 7 * amount);
        this.mic.compressor.knee.value = amount ? 24 : 0;
        this.updateMonitor();
      }
    }

    bindControls() {
      const supportedMic = AudioContextClass && window.AudioWorkletNode
        && window.isSecureContext && navigator.mediaDevices?.getUserMedia;
      byId("mic-toggle").disabled = !supportedMic;
      if (!supportedMic) byId("mic-help").textContent = "Live microphone effects need a current browser on localhost or HTTPS with Web Audio and AudioWorklet support.";
      const supportsOutput = typeof AudioContextClass?.prototype.setSinkId === "function";
      byId("speaker-device").disabled = !supportsOutput;
      byId("speaker-help").textContent = supportsOutput
        ? "Device names become available after microphone permission. Playback volume controls the whole mix."
        : "This browser uses your system output. Change speakers in system sound settings.";
      byId("choose-speakers").hidden = !navigator.mediaDevices?.selectAudioOutput || !supportsOutput;
      byId("refresh-devices").disabled = !navigator.mediaDevices?.enumerateDevices;
      byId("mic-toggle").addEventListener("click", () => {
        if (this.stream) this.stopMicrophone(); else this.startMicrophone();
      });
      byId("mic-device").addEventListener("change", () => { if (this.stream) this.startMicrophone(); });
      byId("mic-monitor").addEventListener("change", () => this.updateMonitor());
      byId("refresh-devices").addEventListener("click", () => this.refreshDevices(true).catch(this.onError));
      byId("speaker-device").addEventListener("change", () => {
        this.setOutput(byId("speaker-device").value).catch((error) => {
          byId("speaker-device").value = this.outputId;
          this.onError(new Error(`Speakers could not change: ${error.message}`));
        });
      });
      byId("choose-speakers").addEventListener("click", async () => {
        byId("choose-speakers").disabled = true;
        try {
          const device = await navigator.mediaDevices.selectAudioOutput();
          if (![...byId("speaker-device").options].some((option) => option.value === device.deviceId)) {
            byId("speaker-device").add(new Option(device.label || "Selected speakers", device.deviceId));
          }
          await this.setOutput(device.deviceId);
        } catch (error) {
          this.onError(new Error(`Speakers could not change: ${error.message}`));
        } finally {
          byId("choose-speakers").disabled = false;
        }
      });
      for (const id of ["volume-input", "speaker-volume"]) {
        byId(id).addEventListener("input", () => this.setMaster(Number(byId(id).value) / 100));
      }
      byId("master-mute").addEventListener("click", () => {
        this.muted = !this.muted;
        byId("master-mute").setAttribute("aria-pressed", String(this.muted));
        byId("master-mute").setAttribute("aria-label", this.muted ? "Unmute speakers" : "Mute speakers");
        byId("master-mute").querySelector("use").setAttribute("href", this.muted ? "#i-muted" : "#i-volume");
        this.setMaster(this.masterLevel);
      });
      document.querySelectorAll("[data-audio-control]").forEach((input) => {
        input.addEventListener("input", () => this.updateEffects());
      });
      document.querySelectorAll("[data-pitch]").forEach((button) => {
        button.addEventListener("click", () => {
          byId("pitch-input").value = button.dataset.pitch;
          this.updateEffects();
        });
      });
      this.updateEffects();
      this.setMaster(this.masterLevel);
    }

    destroy() {
      this.disposed = true;
      this.stopMicrophone();
      this.vocals.pause();
      navigator.mediaDevices?.removeEventListener("devicechange", this.deviceChange);
      if (this.context) this.context.close().catch((error) => console.error("Could not close the audio mixer:", error));
    }
  };
})();
