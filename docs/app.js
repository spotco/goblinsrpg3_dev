const state = {
  manifest: null,
  screens: new Map(),
  current: null,
  muted: false,
  audioUnlocked: false,
  audioElements: new Map(),
  debug: new URLSearchParams(window.location.search).has("debug"),
};

const stage = document.getElementById("stage");
const screenImage = document.getElementById("screen");
const missingRender = document.getElementById("missing-render");
const hotspotsLayer = document.getElementById("hotspots");
const statusOutput = document.getElementById("status");
const restartButton = document.getElementById("restart");
const muteButton = document.getElementById("mute");

if (state.debug) {
  stage.classList.add("debug");
}

function screenId(slide) {
  return `slide-${String(slide).padStart(3, "0")}`;
}

function setStatus(text) {
  statusOutput.value = text;
  statusOutput.textContent = text;
}

function unlockAudio() {
  state.audioUnlocked = true;
}

function prepareAudio() {
  const audioEntries = state.manifest.audio || [];
  for (const entry of audioEntries) {
    if (!entry.outputs || entry.outputs.length === 0) {
      continue;
    }
    const preferred = entry.outputs.find((output) => output.type === "opus") || entry.outputs[0];
    const element = new Audio(preferred.path);
    element.preload = "auto";
    state.audioElements.set(entry.source, element);
  }
}

function stopAudio() {
  for (const element of state.audioElements.values()) {
    element.pause();
    element.currentTime = 0;
  }
}

function updateAudioMute() {
  for (const element of state.audioElements.values()) {
    element.muted = state.muted;
  }
  muteButton.setAttribute("aria-pressed", String(state.muted));
  muteButton.textContent = state.muted ? "Unmute" : "Mute";
}

function navigateTo(id) {
  const next = state.screens.get(id);
  if (!next) {
    return;
  }
  state.current = next;
  renderScreen(next);
}

function renderHotspots(screen) {
  hotspotsLayer.replaceChildren();
  for (const hotspot of screen.hotspots || []) {
    if (!hotspot.bounds || !hotspot.enabled || !hotspot.targetSlide) {
      continue;
    }
    const button = document.createElement("button");
    const bounds = hotspot.bounds;
    button.type = "button";
    button.className = "hotspot";
    button.style.left = `${bounds.x * 100}%`;
    button.style.top = `${bounds.y * 100}%`;
    button.style.width = `${bounds.width * 100}%`;
    button.style.height = `${bounds.height * 100}%`;
    button.dataset.target = screenId(hotspot.targetSlide);
    button.setAttribute("aria-label", hotspot.label || `Go to slide ${hotspot.targetSlide}`);
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      unlockAudio();
      navigateTo(event.currentTarget.dataset.target);
    });
    hotspotsLayer.append(button);
  }
}

function renderScreen(screen) {
  const slideNumber = String(screen.slide).padStart(3, "0");
  screenImage.alt = `Screen ${slideNumber}`;
  screenImage.src = screen.image;
  screenImage.hidden = false;
  missingRender.hidden = true;
  renderHotspots(screen);
  setStatus(`Screen ${slideNumber}`);
}

screenImage.addEventListener("error", () => {
  screenImage.hidden = true;
  missingRender.hidden = false;
});

stage.addEventListener("click", () => {
  unlockAudio();
});

restartButton.addEventListener("click", () => {
  unlockAudio();
  stopAudio();
  navigateTo(state.manifest.startScreen);
});

muteButton.addEventListener("click", () => {
  state.muted = !state.muted;
  updateAudioMute();
});

fetch("game-manifest.json")
  .then((response) => {
    if (!response.ok) {
      throw new Error(`Manifest load failed: ${response.status}`);
    }
    return response.json();
  })
  .then((manifest) => {
    state.manifest = manifest;
    state.screens = new Map(manifest.screens.map((screen) => [screen.id, screen]));
    prepareAudio();
    updateAudioMute();
    navigateTo(manifest.startScreen);
  })
  .catch((error) => {
    setStatus(error.message);
    missingRender.hidden = false;
  });
