(() => {
  "use strict";

  const byId = (id) => document.getElementById(id);
  const video = byId("main-video");
  const form = byId("add-form");
  const rows = new Map();
  const state = {
    songs: [], currentId: null, videoUrl: null, lyricsUrl: null,
    lyrics: [], lyricRequest: 0, refreshing: null, live: false,
    gap: 30, awaitingNext: false, transition: null,
  };
  const audio = new window.KaraokeAudio(video, { onError: showError, onNotice: showNotice });
  const stage = new window.KaraokeStage(video, { getCountdown: () => state.transition, onError: showError });
  let noticeTimer;

  function icon(name) {
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.classList.add("icon");
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#i-${name}`);
    svg.append(use);
    return svg;
  }

  function timeLabel(seconds) {
    const value = Number.isFinite(seconds) ? Math.max(0, Math.floor(seconds)) : 0;
    return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
  }

  function currentSong() {
    return state.songs.find((song) => song.id === state.currentId);
  }

  function playbackUrl(song) {
    return song?.playback_url || song?.video_url || null;
  }

  function showNotice(message) {
    clearTimeout(noticeTimer);
    byId("notice").textContent = message;
    byId("notice").hidden = false;
    noticeTimer = setTimeout(() => { byId("notice").hidden = true; }, 4500);
  }

  function showError(error, target = byId("error-notice")) {
    const message = error instanceof Error ? error.message : String(error);
    console.error("Karaoke studio:", message);
    (target.querySelector("span") || target).textContent = message;
    target.hidden = false;
  }

  function connectionStatus(status, message) {
    byId("connection").dataset.state = status;
    byId("connection-text").textContent = message;
  }

  async function api(url, options = {}) {
    let response;
    try {
      response = await fetch(url, options);
    } catch (error) {
      console.error("Studio request failed:", error);
      throw new Error("Cannot reach the studio. Check the server, then refresh the queue.");
    }
    if (!response.headers.get("content-type")?.includes("application/json")) {
      throw new Error("The studio returned an unexpected response. Refresh the page and try again.");
    }
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || data.description || `Request failed (${response.status}).`);
    return data;
  }

  async function refreshQueue() {
    if (state.refreshing) return state.refreshing;
    state.refreshing = api("/api/queue").then((songs) => {
      updateQueue(songs);
      if (!state.live) connectionStatus("live", "Connected / polling");
      return songs;
    }).finally(() => { state.refreshing = null; });
    return state.refreshing;
  }

  function desiredVolume() {
    return byId("vocals-enabled").checked ? Number(byId("vocals-input").value) / 100 : 0;
  }

  function visualStyle() {
    return document.querySelector('input[name="visual-style"]:checked').value;
  }

  function updateMixControls() {
    const percent = Math.round(desiredVolume() * 100);
    if (byId("vocals-value").textContent !== `${percent}%`) {
      byId("vocals-value").replaceChildren(document.createTextNode(String(percent)));
      const symbol = document.createElement("span");
      symbol.textContent = "%";
      byId("vocals-value").append(symbol);
    }
    byId("vocals-input").disabled = !byId("vocals-enabled").checked;
    byId("vocals-input").setAttribute("aria-valuetext", `${percent}% of original vocals`);
    byId("mix-help").textContent = percent === 0
      ? "Instrumental only. Adjust this slider to hear the original voice live."
      : `${percent}% original voice, live. Create a separate export to save this vocal guide.`;
    document.querySelectorAll("[data-volume]").forEach((button) => {
      button.setAttribute("aria-pressed", String(Number(button.dataset.volume) === percent));
    });
    const song = currentSong();
    const button = byId("apply-mix");
    button.disabled = !song?.video_url || song.status !== "READY"
      || (song.rendered_vocals_volume === desiredVolume() && !song.error);
    button.replaceChildren(document.createTextNode(percent === 0 ? "Use instrumental" : "Create vocal mix"), icon("arrow"));
    audio.setVocalLevel(desiredVolume()).catch(showError);
    if (playbackUrl(song)) {
      byId("now-playing-meta").textContent = `${song.performer ? `${song.performer} / ` : ""}${timeLabel(song.duration)} / ${percent}% original vocals / Live mix`;
      byId("preview-tag").textContent = `${percent === 0 ? "Instrumental" : `${percent}% vocal guide`} / Live`;
    }
  }

  function setMixVolume(percent) {
    byId("vocals-enabled").checked = percent > 0;
    byId("vocals-input").value = String(percent);
    updateMixControls();
  }

  function setSourceMode() {
    const upload = document.querySelector('input[name="source-mode"]:checked').value === "upload";
    byId("youtube-fields").hidden = upload;
    byId("upload-fields").hidden = !upload;
    byId("url-input").disabled = upload;
    byId("url-input").required = !upload;
    byId("audio-input").disabled = !upload;
    byId("audio-input").required = upload;
    byId("lyrics-upload-label").hidden = !upload;
    byId("lyrics-input").disabled = !upload;
    byId("source-help").textContent = upload
      ? "WAV, MP3, FLAC and more, up to 250 MB. Use audio you are authorized to process."
      : "Use audio you are authorized to process. We'll separate the vocals and sync the lyrics.";
    byId("form-error").hidden = true;
    byId("url-input").removeAttribute("aria-invalid");
  }

  function syncTimeline() {
    const duration = Number.isFinite(video.duration) ? video.duration : (currentSong()?.duration || 0);
    byId("elapsed-time").textContent = timeLabel(video.currentTime);
    byId("duration-time").textContent = timeLabel(duration);
    byId("seek-input").disabled = !state.videoUrl || !duration;
    byId("seek-input").value = duration ? String(Math.round(video.currentTime / duration * 1000)) : "0";
    byId("seek-input").setAttribute("aria-valuetext", `${timeLabel(video.currentTime)} of ${timeLabel(duration)}`);
    state.lyrics.forEach((line, index) => {
      const row = byId("lyric-list").children[index];
      if (row) row.dataset.active = String(line.start <= video.currentTime && video.currentTime < line.end);
    });
  }

  function updatePlayButton() {
    const playing = !video.paused && !video.ended;
    byId("play-toggle").dataset.playing = String(playing);
    byId("play-toggle").setAttribute("aria-label", playing ? "Pause song" : "Play song");
    byId("play-toggle").replaceChildren(icon(playing ? "pause" : "play"));
    renderRows();
  }

  async function startPlayback() {
    cancelCountdown();
    try {
      await audio.resume();
      await video.play();
    } catch (error) {
      if (error.name === "NotAllowedError") {
        showNotice("Your song is ready. Press play to start the video.");
      } else {
        showError(new Error(`Playback could not start: ${error.message}`));
      }
    }
  }

  async function loadLyrics(url) {
    const requestId = ++state.lyricRequest;
    try {
      const lyrics = await api(url);
      if (requestId !== state.lyricRequest) return;
      state.lyrics = lyrics;
      byId("lyric-list").replaceChildren();
      lyrics.forEach((line) => {
        const row = document.createElement("li");
        const button = document.createElement("button");
        button.type = "button";
        button.setAttribute("aria-label", `Seek to ${line.text}`);
        const time = document.createElement("span");
        time.className = "lyric-time";
        time.textContent = timeLabel(line.start);
        button.append(time, document.createTextNode(line.text));
        button.addEventListener("click", () => { video.currentTime = line.start; syncTimeline(); });
        row.append(button);
        byId("lyric-list").append(row);
      });
      byId("lyric-details").hidden = false;
      syncTimeline();
    } catch (error) {
      if (requestId === state.lyricRequest) showError(error);
    }
  }

  function updatePreview(song) {
    const playable = Boolean(playbackUrl(song));
    const busy = song && ["QUEUED", "DOWNLOADING", "PROCESSING"].includes(song.status);
    const failed = song?.status === "ERROR";
    video.hidden = !playable;
    byId("no-video-placeholder").hidden = playable || busy || failed;
    byId("processing-overlay").hidden = playable || (!busy && !failed);
    byId("processing-title").textContent = failed ? "This song needs another try" : (song?.stage || "Preparing your song");
    byId("processing-description").textContent = failed
      ? (song.error || "Retry the song from the queue below.")
      : (song?.progress >= 65 ? "Vocals separated. Lyrics synced. Building your MP4." : "Separating the track and finding the words.");
    byId("processing-progress").value = song?.progress || 0;
    byId("processing-progress").hidden = Boolean(failed);
    byId("processing-overlay").querySelector(".processing-spinner").hidden = Boolean(failed);
    byId("now-playing-title").textContent = song?.title || song?.url || "No song selected";
    byId("now-playing-title").title = song?.title || song?.url || "";
    const percent = Math.round((song?.rendered_vocals_volume || 0) * 100);
    byId("now-playing-meta").textContent = playable
      ? `${timeLabel(song.duration)} / ${percent === 0 ? "Instrumental only" : `${percent}% original vocals`} / MP4`
      : (song?.stage || "Your instrumental will appear here.");
    byId("preview-tag").textContent = playable
      ? `${percent === 0 ? "Instrumental" : `${percent}% vocal guide`} / Lyrics synced`
      : (song?.stage || "Waiting for your song");
    byId("play-toggle").disabled = !playable;
    byId("fullscreen-btn").disabled = !playable;
    byId("download-instrumental").hidden = !song?.instrumental_url;
    if (song?.instrumental_url) byId("download-instrumental").href = song.instrumental_url;
    byId("download-mix").hidden = !song?.mix_url;
    if (song?.mix_url) {
      byId("download-mix").href = song.mix_url;
      byId("download-mix").querySelector("span").textContent = `Download ${percent}% vocal mix`;
    }
    byId("download-lyrics").hidden = !song?.lyrics_url;
    if (song?.lyrics_url) byId("download-lyrics").href = `${song.lyrics_url}&download=1`;
    byId("mix-error").hidden = !playable || !song?.error;
    byId("mix-error").textContent = playable ? (song?.error || "") : "";
    updateMixControls();
  }

  function selectSong(song, { play = false, preservePlayback = false, syncMix = true } = {}) {
    const changedSong = state.currentId !== song.id;
    if (changedSong || play) cancelCountdown();
    state.currentId = song.id;
    audio.setSong(song.vocals_audio_url);
    if (syncMix) {
      setMixVolume(Math.round(song.vocals_volume * 100));
      document.querySelector(`input[name="visual-style"][value="${song.visual_style}"]`).checked = true;
    }
    if (changedSong) {
      state.lyrics = [];
      state.lyricsUrl = null;
      ++state.lyricRequest;
      byId("lyric-list").replaceChildren();
      byId("lyric-details").open = false;
      byId("lyric-details").hidden = true;
    }
    const url = playbackUrl(song);
    if (url && url !== state.videoUrl) {
      const previousTime = preservePlayback ? video.currentTime : 0;
      const resume = preservePlayback && !video.paused;
      video.pause();
      state.videoUrl = url;
      video.src = url;
      video.addEventListener("loadedmetadata", () => {
        if (state.videoUrl !== url) return;
        video.currentTime = Math.min(previousTime, video.duration || 0);
        syncTimeline();
        if (play || resume) startPlayback();
      }, { once: true });
    } else if (play && url) {
      startPlayback();
    }
    if (song.lyrics_url && song.lyrics_url !== state.lyricsUrl) {
      state.lyricsUrl = song.lyrics_url;
      loadLyrics(song.lyrics_url);
    }
    updatePreview(song);
    renderRows();
  }

  function resetSelection() {
    cancelCountdown();
    video.pause();
    video.removeAttribute("src");
    video.load();
    audio.setSong(null);
    state.currentId = null;
    state.videoUrl = null;
    state.lyrics = [];
    state.lyricsUrl = null;
    ++state.lyricRequest;
    byId("lyric-details").hidden = true;
    byId("lyric-list").replaceChildren();
    updatePreview(null);
    syncTimeline();
  }

  function cancelCountdown() {
    state.awaitingNext = false;
    state.transition = null;
    byId("countdown-overlay").hidden = true;
    byId("countdown-announcement").textContent = "";
    stage.sync();
  }

  function reconcileCountdown() {
    if (!state.awaitingNext) return;
    const index = state.songs.findIndex((song) => song.id === state.currentId);
    const following = state.songs.slice(index + 1);
    const next = following.find((song) => song.status === "READY" && playbackUrl(song));
    if (!next) {
      const pending = following.find((song) => ["QUEUED", "DOWNLOADING", "PROCESSING"].includes(song.status));
      state.transition = {
        nextId: null, deadline: null, waiting: true,
        performer: pending?.performer || "Next singer",
        title: pending ? (pending.title || "Preparing the next song") : "Add the next song to the queue",
        label: pending ? "GETTING THE NEXT SONG READY" : "WAITING FOR THE NEXT SONG",
      };
    } else if (state.transition?.nextId !== next.id) {
      state.transition = {
        nextId: next.id, deadline: Date.now() + state.gap * 1000, waiting: false,
        performer: next.performer || "Next singer", title: next.title || "Next song",
        label: "UP NEXT",
      };
      byId("countdown-announcement").textContent = `Up next: ${state.transition.performer}, ${state.transition.title}. Starts in ${state.gap} seconds.`;
    }
    renderCountdown();
  }

  function renderCountdown() {
    const transition = state.transition;
    if (!state.awaitingNext || !transition) return;
    const seconds = transition.waiting ? null : Math.max(0, Math.ceil((transition.deadline - Date.now()) / 1000));
    byId("countdown-overlay").hidden = false;
    byId("next-singer").textContent = transition.performer;
    byId("next-song").textContent = transition.title;
    byId("countdown-seconds").textContent = seconds === null ? "--" : String(seconds);
    byId("countdown-label").textContent = transition.label;
    byId("start-next").disabled = transition.waiting;
    if (seconds === 0) startNextSong();
    else stage.sync();
  }

  function startNextSong() {
    const next = state.songs.find((song) => song.id === state.transition?.nextId);
    if (next?.status === "READY" && playbackUrl(next)) selectSong(next, { play: true });
    else reconcileCountdown();
  }

  function queueButton(action, symbol) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `icon-button action-${action}`;
    button.dataset.action = action;
    button.append(icon(symbol));
    return button;
  }

  function createRow(id) {
    const row = document.createElement("li");
    row.className = "queue-item";
    row.dataset.id = id;
    for (const className of ["queue-number", "queue-art", "queue-info", "queue-status", "queue-actions", "queue-error"]) {
      const element = document.createElement("div");
      element.className = className;
      row.append(element);
    }
    row.querySelector(".queue-art").append(icon("music"));
    const title = document.createElement("p");
    title.className = "queue-title";
    const subtitle = document.createElement("p");
    subtitle.className = "queue-subtitle";
    const progress = document.createElement("progress");
    progress.className = "queue-progress";
    progress.max = 100;
    row.querySelector(".queue-info").append(title, subtitle, progress);
    for (const [action, symbol] of [["play", "play"], ["retry", "refresh"], ["up", "up"], ["down", "down"], ["remove", "remove"]]) {
      row.querySelector(".queue-actions").append(queueButton(action, symbol));
    }
    return row;
  }

  function renderRows() {
    const list = byId("queue-list");
    for (const [id, row] of rows) {
      if (!state.songs.some((song) => song.id === id)) { row.remove(); rows.delete(id); }
    }
    state.songs.forEach((song, index) => {
      let row = rows.get(song.id);
      if (!row) { row = createRow(song.id); rows.set(song.id, row); }
      row.dataset.status = song.status;
      row.dataset.selected = String(song.id === state.currentId);
      const title = song.title || song.url || "Local track";
      const busy = ["DOWNLOADING", "PROCESSING"].includes(song.status);
      const playing = song.id === state.currentId && !video.paused && !video.ended;
      row.querySelector(".queue-number").textContent = String(index + 1).padStart(2, "0");
      row.querySelector(".queue-title").textContent = title;
      row.querySelector(".queue-title").title = title;
      row.querySelector(".queue-subtitle").textContent = busy
        ? `${song.performer ? `${song.performer} / ` : ""}${song.stage}`
        : `${song.performer ? `${song.performer} / ` : ""}${song.source === "upload" ? "Local file" : "YouTube"} / ${Math.round(song.vocals_volume * 100)}% vocal guide`;
      row.querySelector(".queue-status").textContent = busy ? `${song.progress}%` : playing ? "Playing" : ({
        QUEUED: "Queued", READY: "Ready", ERROR: "Failed", PLAYING: "Playing", DONE: "Played",
      }[song.status] || song.status);
      const progress = row.querySelector("progress");
      progress.hidden = !busy;
      progress.value = song.progress;
      progress.setAttribute("aria-label", `Processing ${title}`);
      const error = row.querySelector(".queue-error");
      error.textContent = song.error || "";
      error.hidden = !song.error;
      for (const [action, label] of [["play", "Play"], ["retry", "Retry"], ["up", "Move up"], ["down", "Move down"], ["remove", "Remove"]]) {
        const button = row.querySelector(`.action-${action}`);
        button.setAttribute("aria-label", `${label} ${title}`);
        button.title = `${label} ${title}`;
        button.hidden = action === "play" ? !song.video_url
          : action === "retry" ? song.status !== "ERROR"
          : ["up", "down"].includes(action) ? song.status !== "QUEUED" || Boolean(song.video_url) : busy;
        const neighbor = state.songs[index + (action === "up" ? -1 : 1)];
        button.disabled = ["up", "down"].includes(action)
          && (!neighbor || neighbor.status !== "QUEUED" || Boolean(neighbor.video_url));
      }
      if (list.children[index] !== row) list.insertBefore(row, list.children[index] || null);
    });
    list.hidden = state.songs.length === 0;
    byId("empty-queue").hidden = state.songs.length !== 0;
    byId("queue-count").textContent = `${state.songs.length} ${state.songs.length === 1 ? "song" : "songs"}`;
    byId("nav-count").textContent = String(state.songs.length);
  }

  function updateQueue(songs) {
    if (!Array.isArray(songs)) throw new Error("The studio returned an invalid song queue.");
    const previousSongs = state.songs;
    state.songs = songs;
    if (state.currentId && !currentSong()) resetSelection();
    const selected = currentSong();
    if (selected?.status === "ERROR" && songs.some((song) => song.video_url)) {
      selectSong(songs.find((song) => song.video_url));
    } else if (!selected && songs.length) {
      selectSong(songs.find((song) => song.video_url) || songs[0]);
    } else if (playbackUrl(selected) !== state.videoUrl && playbackUrl(selected)) {
      selectSong(selected, { preservePlayback: true, syncMix: false });
    } else {
      updatePreview(selected);
      renderRows();
    }
    reconcileCountdown();
    if (songs.some((song) => {
      const previous = previousSongs.find((entry) => entry.id === song.id);
      return song.status === "READY" && !song.error && song.rendered_vocals_volume > 0
        && previous?.video_url && previous.status !== "READY";
    })) showNotice("Vocal mix ready to download.");
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    byId("add-btn").disabled = true;
    byId("add-btn").querySelector("span").textContent = "Adding song";
    byId("form-error").hidden = true;
    try {
      const options = {
        title: byId("title-input").value.trim(), performer: byId("performer-input").value.trim(),
        vocals_volume: desiredVolume(), visual_style: visualStyle(),
      };
      const upload = document.querySelector('input[name="source-mode"]:checked').value === "upload";
      if (upload) {
        const audio = byId("audio-input").files[0];
        if (!audio) throw new Error("Choose an audio or video file first.");
        const data = new FormData();
        data.append("audio", audio);
        Object.entries(options).forEach(([key, value]) => data.append(key, String(value)));
        if (byId("lyrics-input").files[0]) data.append("lyrics", byId("lyrics-input").files[0]);
        await api("/api/queue/upload", { method: "POST", body: data });
      } else {
        await api("/api/queue", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ...options, url: byId("url-input").value.trim() }),
        });
      }
      byId("url-input").value = "";
      byId("title-input").value = "";
      byId("performer-input").value = "";
      byId("audio-input").value = "";
      byId("lyrics-input").value = "";
      byId("optional-settings").open = false;
      showNotice("Song added to queue. We'll get the stage ready.");
      await refreshQueue();
    } catch (error) {
      showError(error, byId("form-error"));
      if (!byId("url-input").disabled) byId("url-input").setAttribute("aria-invalid", "true");
    } finally {
      byId("add-btn").disabled = false;
      byId("add-btn").querySelector("span").textContent = "Add to queue";
    }
  });

  byId("queue-list").addEventListener("click", async (event) => {
    const button = event.target.closest("button[data-action]");
    if (!button || button.disabled) return;
    const song = state.songs.find((song) => song.id === button.closest(".queue-item").dataset.id);
    if (!song) return;
    if (button.dataset.action === "play") { selectSong(song, { play: true }); return; }
    button.disabled = true;
    try {
      await api(`/api/queue/${song.id}${button.dataset.action === "remove" ? "" : `/${button.dataset.action}`}`, {
        method: button.dataset.action === "remove" ? "DELETE" : "POST",
      });
      await refreshQueue();
    } catch (error) {
      showError(error);
    } finally {
      renderRows();
    }
  });

  byId("apply-mix").addEventListener("click", async () => {
    const song = currentSong();
    if (!song) { showError(new Error("Select a ready song to create a vocal mix.")); return; }
    const volume = desiredVolume();
    byId("apply-mix").disabled = true;
    try {
      const result = await api(`/api/queue/${song.id}/mix`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vocals_volume: volume }),
      });
      await refreshQueue();
      const updated = state.songs.find((entry) => entry.id === song.id) || result;
      showNotice(volume === 0 ? "Instrumental selected."
        : updated.status === "READY" && updated.rendered_vocals_volume === volume
          ? "Vocal mix ready to download." : "Creating your separate vocal mix.");
    } catch (error) {
      showError(error);
    } finally {
      updateMixControls();
    }
  });

  byId("refresh-btn").addEventListener("click", () => refreshQueue().catch(showError));
  byId("dismiss-error").addEventListener("click", () => { byId("error-notice").hidden = true; });
  form.addEventListener("input", () => {
    byId("form-error").hidden = true;
    byId("url-input").removeAttribute("aria-invalid");
  });
  document.querySelectorAll('input[name="source-mode"]').forEach((input) => input.addEventListener("change", setSourceMode));
  byId("vocals-enabled").addEventListener("change", () => {
    if (byId("vocals-enabled").checked && Number(byId("vocals-input").value) === 0) byId("vocals-input").value = "25";
    updateMixControls();
  });
  byId("vocals-input").addEventListener("input", updateMixControls);
  document.querySelectorAll("[data-volume]").forEach((button) => button.addEventListener("click", () => setMixVolume(Number(button.dataset.volume))));
  document.querySelectorAll('input[name="visual-style"]').forEach((input) => input.addEventListener("change", () => {
    byId("video-wrapper").dataset.style = visualStyle();
  }));
  byId("play-toggle").addEventListener("click", () => { if (video.paused) startPlayback(); else video.pause(); });
  byId("start-next").addEventListener("click", startNextSong);
  byId("cancel-countdown").addEventListener("click", () => {
    cancelCountdown();
    showNotice("Countdown held. Press play or choose a song from the queue when you are ready.");
  });
  byId("song-gap").addEventListener("change", () => {
    const input = byId("song-gap");
    const seconds = input.valueAsNumber;
    if (!Number.isSafeInteger(seconds) || seconds < 0 || !Number.isSafeInteger(Date.now() + seconds * 1000)) {
      input.setAttribute("aria-invalid", "true");
      showError(new Error(`Enter a whole number of seconds, zero or greater. The countdown is still ${state.gap} seconds.`), byId("playback-error"));
      return;
    }
    input.removeAttribute("aria-invalid");
    byId("playback-error").hidden = true;
    state.gap = seconds;
    if (state.transition && !state.transition.waiting) state.transition.deadline = Date.now() + seconds * 1000;
    renderCountdown();
  });
  byId("seek-input").addEventListener("input", () => {
    if (Number.isFinite(video.duration)) { video.currentTime = video.duration * Number(byId("seek-input").value) / 1000; syncTimeline(); }
  });
  byId("fullscreen-btn").addEventListener("click", async () => {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (byId("stage-shell").requestFullscreen) await byId("stage-shell").requestFullscreen();
      else throw new Error("Full screen is not supported by this browser. Download the MP4 to play it full screen.");
    } catch (error) { showError(error); }
  });
  document.addEventListener("fullscreenchange", () => {
    byId("fullscreen-btn").setAttribute("aria-label", document.fullscreenElement ? "Exit full screen" : "Full screen");
  });
  ["timeupdate", "loadedmetadata", "durationchange", "seeked"].forEach((event) => video.addEventListener(event, syncTimeline));
  ["play", "pause", "ended"].forEach((event) => video.addEventListener(event, updatePlayButton));
  video.addEventListener("error", () => {
    if (state.videoUrl) showError(new Error("This video could not be played. Try the MP4 download or refresh the queue."));
  });
  video.addEventListener("ended", () => {
    state.awaitingNext = true;
    reconcileCountdown();
  });

  setSourceMode();
  setMixVolume(Math.round(Number(document.body.dataset.defaultVocals) * 100));
  const defaultStyle = document.body.dataset.defaultStyle;
  document.querySelector(`input[name="visual-style"][value="${defaultStyle}"]`).checked = true;
  byId("video-wrapper").dataset.style = defaultStyle;
  byId("add-btn").disabled = false;
  video.controls = false;
  refreshQueue().catch((error) => { connectionStatus("offline", "Offline"); showError(error); });
  if (typeof io === "function") {
    const socket = io();
    socket.on("connect", () => { state.live = true; connectionStatus("live", "Live studio"); });
    socket.on("disconnect", () => { state.live = false; connectionStatus("offline", "Reconnecting"); });
    socket.on("connect_error", (error) => {
      state.live = false;
      console.warn("Live updates disconnected:", error.message);
      connectionStatus("offline", "Reconnecting");
    });
    socket.on("queue_update", updateQueue);
  } else {
    showError(new Error("Live updates could not load. The queue will refresh automatically."));
  }
  const polling = setInterval(() => {
    if (document.visibilityState === "visible") refreshQueue().catch((error) => {
      connectionStatus("offline", "Offline");
      console.warn(error.message);
    });
  }, 5000);
  const countdownClock = setInterval(renderCountdown, 200);
  window.addEventListener("pagehide", () => {
    clearInterval(polling);
    clearInterval(countdownClock);
    clearTimeout(noticeTimer);
    audio.destroy();
    stage.destroy();
  });
  window.addEventListener("pageshow", (event) => { if (event.persisted) location.reload(); });
})();
