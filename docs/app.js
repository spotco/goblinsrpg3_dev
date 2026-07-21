const state = {
  manifest: null,
  screens: new Map(),
  current: null,
  muted: false,
  audioUnlocked: false,
  audioElements: new Map(),
  animations: null,
  animationSlides: new Map(),
  animationQueue: [],
  animationTimers: [],
  currentLayerElements: new Map(),
  debug: new URLSearchParams(window.location.search).has("debug"),
};

const stage = document.getElementById("stage");
const screenImage = document.getElementById("screen");
const layersLayer = document.getElementById("layers");
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

function clearAnimationTimers() {
  for (const timer of state.animationTimers) {
    window.clearTimeout(timer);
  }
  state.animationTimers = [];
  state.animationQueue = [];
}

function scheduleAnimation(callback, delayMs = 0) {
  const timer = window.setTimeout(callback, Math.max(delayMs, 0));
  state.animationTimers.push(timer);
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

async function loadAnimations(manifest) {
  const animationStatus = manifest.animationStatus;
  if (!animationStatus || animationStatus.status !== "available" || !animationStatus.path) {
    return null;
  }
  const response = await fetch(animationStatus.path);
  if (!response.ok) {
    throw new Error(`Animation manifest load failed: ${response.status}`);
  }
  return response.json();
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

function positionLayerElement(element, layer) {
  const bounds = layer.bounds;
  element.className = `layer layer-${layer.type}`;
  element.style.left = `${bounds.x * 100}%`;
  element.style.top = `${bounds.y * 100}%`;
  element.style.width = `${bounds.width * 100}%`;
  element.style.height = `${bounds.height * 100}%`;
  element.style.zIndex = String(layer.zOrder ?? 0);
  element.dataset.layerId = layer.id;
  element.dataset.shapeId = String(layer.shapeId);
  element.dataset.animated = String(Boolean(layer.animated));
}

function renderLayers(screen) {
  layersLayer.replaceChildren();
  state.currentLayerElements = new Map();
  const layers = screen.layers || [];
  for (const layer of layers) {
    const element = document.createElement("div");
    positionLayerElement(element, layer);
    if (layer.type === "image" && layer.instancePath) {
      const image = document.createElement("img");
      image.className = "layer-image";
      image.src = layer.instancePath;
      image.alt = "";
      image.decoding = "async";
      image.draggable = false;
      element.append(image);
    } else if (layer.type === "text") {
      element.textContent = layer.text || "";
      element.style.fontSize = `${Math.max(layer.bounds.height * 72, 1)}cqh`;
    }
    state.currentLayerElements.set(String(layer.shapeId), element);
    layersLayer.append(element);
  }
  return layers.length > 0;
}

function parsedStrings(items) {
  const values = [];
  for (const item of items || []) {
    const parsed = item.parsed;
    if (parsed && typeof parsed.stringValue === "string") {
      values.push(parsed.stringValue);
    }
  }
  return values;
}

function nodeDelay(node) {
  let delay = 0;
  for (const condition of node.conditions || []) {
    const parsed = condition.parsed;
    if (parsed && Number.isFinite(parsed.delayMs) && parsed.delayMs > delay) {
      delay = parsed.delayMs;
    }
  }
  return delay;
}

function nodeWaitsForClick(node) {
  return (node.conditions || []).some((condition) => {
    const event = condition.parsed && condition.parsed.triggerEvent;
    return event === 9 || event === 10;
  });
}

function targetsFor(node, behavior) {
  const targets = behavior.targets && behavior.targets.length ? behavior.targets : node.targets || [];
  return targets
    .filter((target) => target.kind === "shape" && target.shapeId !== undefined)
    .map((target) => state.currentLayerElements.get(String(target.shapeId)))
    .filter(Boolean);
}

function nodeDuration(node) {
  const parsed = node.timeNode && node.timeNode.parsed;
  if (!parsed || !Number.isFinite(parsed.durationMs) || parsed.durationMs <= 1) {
    return 1;
  }
  return parsed.durationMs;
}

function applySetBehavior(elements, strings) {
  if (!strings.includes("style.visibility")) {
    return;
  }
  const visibility = strings.includes("hidden") ? "hidden" : strings.includes("visible") ? "visible" : null;
  if (!visibility) {
    return;
  }
  for (const element of elements) {
    element.style.visibility = visibility;
    if (visibility === "visible") {
      element.style.opacity = element.style.opacity || "1";
    }
  }
}

function applyEffectBehavior(elements, strings, duration) {
  if (!strings.some((value) => value === "fade" || value === "dissolve")) {
    return;
  }
  for (const element of elements) {
    element.style.visibility = "visible";
    element.style.opacity = "0";
    element.style.transition = `opacity ${duration}ms linear`;
    window.requestAnimationFrame(() => {
      element.style.opacity = "1";
    });
  }
}

function applyBehavior(node, behavior) {
  const elements = targetsFor(node, behavior);
  if (elements.length === 0) {
    return;
  }
  const strings = parsedStrings(behavior.variants);
  const duration = nodeDuration(node);
  if (behavior.kind === "set") {
    applySetBehavior(elements, strings);
  } else if (behavior.kind === "effect") {
    applyEffectBehavior(elements, strings, duration);
  }
}

function runAnimationNode(node, baseDelay = 0, allowClickNode = false) {
  if (nodeWaitsForClick(node) && !allowClickNode) {
    state.animationQueue.push(node);
    return;
  }
  const startDelay = baseDelay + nodeDelay(node);
  if (node.behaviors && node.behaviors.length) {
    scheduleAnimation(() => {
      for (const behavior of node.behaviors) {
        applyBehavior(node, behavior);
      }
    }, startDelay);
  }
  for (const child of node.children || []) {
    runAnimationNode(child, startDelay, false);
  }
}

function setupAnimations(screen) {
  clearAnimationTimers();
  for (const element of state.currentLayerElements.values()) {
    element.style.visibility = "";
    element.style.opacity = "";
    element.style.transition = "";
    element.style.transform = "";
  }
  const slideAnimations = state.animationSlides.get(screen.slide);
  if (!slideAnimations) {
    return;
  }
  for (const node of slideAnimations.rootTimeNodes || []) {
    runAnimationNode(node, 0, false);
  }
}

function advanceAnimation() {
  const node = state.animationQueue.shift();
  if (!node) {
    return false;
  }
  runAnimationNode(node, 0, true);
  return true;
}

function renderScreen(screen) {
  const slideNumber = String(screen.slide).padStart(3, "0");
  const renderedLayers = renderLayers(screen);
  screenImage.alt = `Screen ${slideNumber}`;
  screenImage.src = screen.image;
  screenImage.hidden = renderedLayers;
  layersLayer.hidden = !renderedLayers;
  missingRender.hidden = true;
  setupAnimations(screen);
  renderHotspots(screen);
  setStatus(`Screen ${slideNumber}`);
}

screenImage.addEventListener("error", () => {
  screenImage.hidden = true;
  missingRender.hidden = false;
});

stage.addEventListener("click", () => {
  unlockAudio();
  advanceAnimation();
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
    return loadAnimations(manifest).then((animations) => {
      state.animations = animations;
      state.animationSlides = new Map((animations?.slides || []).map((slide) => [slide.slide, slide]));
      navigateTo(manifest.startScreen);
    });
  })
  .catch((error) => {
    setStatus(error.message);
    missingRender.hidden = false;
  });
